"""
Workflow runner — the central state machine

Prepare functions validate state and mark rows ``processing`` (sync, called from
API routes). Execute functions perform LLM work (async via jobs.enqueue).

Raises:
    ValueError   — invalid state transition or missing data (→ HTTP 400)
    LLMError     — LLM call failed after retries (→ HTTP 500 on sync paths only)
                   The service layer already persisted the error state before
                   re-raising, so no additional DB cleanup is needed on execute.
"""

import logging
import re

from app.core.database import get_client
from app.llm.client import LLMError
from app.services.chapter import generate_chapter as _gen_chapter
from app.services.chapter import generate_summary as _gen_summary
from app.services.compilation import compile_book as _compile
from app.services.log import log_event
from app.services.outline import generate_outline as _gen_outline

logger = logging.getLogger(__name__)

# Matches lines like "Chapter 3: The Road Ahead" (case-insensitive).
_CHAPTER_RE = re.compile(
    r"^Chapter\s+(\d+)\s*:\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

# ── helpers ──


def _parse_chapters(outline: str) -> list[tuple[int, str]]:
    """Return [(chapter_index, title), …] extracted from the outline text."""
    matches = _CHAPTER_RE.findall(outline)
    return [(int(num), title.strip()) for num, title in matches]


def _get_book(book_id: str) -> dict:
    resp = get_client().table("books").select("*").eq("id", book_id).execute()
    if not resp.data:
        raise ValueError(f"Book {book_id!r} not found")
    return resp.data[0]


def _get_chapter(chapter_id: str) -> dict:
    resp = get_client().table("chapters").select("*").eq("id", chapter_id).execute()
    if not resp.data:
        raise ValueError(f"Chapter {chapter_id!r} not found")
    return resp.data[0]


def _reject_if_processing(status: str, label: str) -> None:
    if status == "processing":
        raise ValueError(f"{label} is already in progress. Please wait.")


# ── outline stage ──


def prepare_outline_generation(book_id: str) -> None:
    """Validate and mark the outline as processing before background generation."""
    book = _get_book(book_id)
    _reject_if_processing(book["outline_status"], "Outline generation")
    allowed = {"pending", "error"}
    if book["outline_status"] not in allowed:
        raise ValueError(
            f"Cannot generate outline: current status is {book['outline_status']!r}. "
            f"Expected one of {allowed}."
        )
    get_client().table("books").update(
        {"outline_status": "processing", "error_message": None}
    ).eq("id", book_id).execute()


def execute_outline_generation(book_id: str) -> None:
    _gen_outline(book_id)


def prepare_submit_outline_notes(book_id: str, notes: str) -> None:
    if not notes or not notes.strip():
        raise ValueError("Revision notes cannot be empty")

    book = _get_book(book_id)
    _reject_if_processing(book["outline_status"], "Outline generation")
    if book["outline_status"] != "in_review":
        raise ValueError(
            f"Cannot submit outline notes: current status is "
            f"{book['outline_status']!r}. Expected 'in_review'."
        )

    get_client().table("books").update(
        {
            "notes_after_outline": notes.strip(),
            "outline_status": "processing",
            "error_message": None,
        }
    ).eq("id", book_id).execute()

    log_event(
        "outline_revision_requested", "Editor submitted revision notes", book_id=book_id
    )


def prepare_approve_outline(book_id: str) -> str | None:
    """
    Approve the outline, create chapter rows, and mark the first chapter processing.

    Returns the first chapter id to generate, or None if no chapter row exists.
    """
    book = _get_book(book_id)
    _reject_if_processing(book["outline_status"], "Outline approval")
    if book["outline_status"] != "in_review":
        raise ValueError(
            f"Cannot approve outline: current status is "
            f"{book['outline_status']!r}. Expected 'in_review'."
        )

    outline = book.get("outline") or ""
    parsed = _parse_chapters(outline)
    if not parsed:
        raise ValueError(
            "Could not parse any chapters from the outline. "
            "The outline may not follow the expected format."
        )

    db = get_client()

    db.table("books").update({"outline_status": "approved"}).eq("id", book_id).execute()
    log_event(
        "outline_approved",
        f"Outline approved; {len(parsed)} chapters parsed",
        book_id=book_id,
    )

    min_index = parsed[0][0]
    for chapter_index, chapter_title in parsed:
        exists = (
            db.table("chapters")
            .select("id")
            .eq("book_id", book_id)
            .eq("chapter_index", chapter_index)
            .execute()
        )
        if not exists.data:
            db.table("chapters").insert(
                {
                    "book_id": book_id,
                    "chapter_index": chapter_index,
                    "title": chapter_title,
                    "status": "pending",
                }
            ).execute()
        if chapter_index < min_index:
            min_index = chapter_index

    first = (
        db.table("chapters")
        .select("id")
        .eq("book_id", book_id)
        .eq("chapter_index", min_index)
        .execute()
    )
    if not first.data:
        return None

    chapter_id = first.data[0]["id"]
    db.table("chapters").update(
        {"status": "processing", "error_message": None}
    ).eq("id", chapter_id).execute()
    return chapter_id


def execute_chapter_generation(chapter_id: str) -> None:
    _gen_chapter(chapter_id)


# ── chapter stage ──


def prepare_approve_chapter(chapter_id: str) -> None:
    chapter = _get_chapter(chapter_id)
    _reject_if_processing(chapter["status"], "Chapter workflow")
    if chapter["status"] != "in_review":
        raise ValueError(
            f"Cannot approve chapter: current status is "
            f"{chapter['status']!r}. Expected 'in_review'."
        )

    get_client().table("chapters").update({"status": "approved"}).eq(
        "id", chapter_id
    ).execute()
    log_event(
        "chapter_approved",
        f"Chapter {chapter['chapter_index']} approved",
        book_id=chapter["book_id"],
        chapter_id=chapter_id,
    )


def execute_continue_after_chapter_approval(chapter_id: str) -> None:
    """
    Generate summary, then the next pending chapter or mark the book ready to compile.

    Summary failure is non-fatal: the chapter stays approved and the workflow
    continues, but the missing summary will reduce LLM context for later chapters.
    """
    chapter = _get_chapter(chapter_id)
    book_id = chapter["book_id"]
    db = get_client()

    try:
        _gen_summary(chapter_id)
    except LLMError as exc:
        logger.warning(
            "Summary generation failed for chapter %s (continuing): %s",
            chapter_id,
            exc,
        )
        db.table("chapters").update(
            {"error_message": f"Summary generation failed: {exc}"}
        ).eq("id", chapter_id).execute()

    next_ch = (
        db.table("chapters")
        .select("id")
        .eq("book_id", book_id)
        .eq("status", "pending")
        .order("chapter_index")
        .limit(1)
        .execute()
    )
    if next_ch.data:
        next_id = next_ch.data[0]["id"]
        db.table("chapters").update(
            {"status": "processing", "error_message": None}
        ).eq("id", next_id).execute()
        _gen_chapter(next_id)
        return

    not_done = (
        db.table("chapters")
        .select("id")
        .eq("book_id", book_id)
        .neq("status", "approved")
        .execute()
    )
    if not not_done.data:
        db.table("books").update({"final_status": "in_review"}).eq(
            "id", book_id
        ).execute()
        log_event(
            "all_chapters_approved",
            "All chapters approved; book ready for final compilation",
            book_id=book_id,
        )


def prepare_submit_chapter_notes(chapter_id: str, notes: str) -> None:
    if not notes or not notes.strip():
        raise ValueError("Revision notes cannot be empty")

    chapter = _get_chapter(chapter_id)
    _reject_if_processing(chapter["status"], "Chapter generation")
    if chapter["status"] != "in_review":
        raise ValueError(
            f"Cannot submit chapter notes: current status is "
            f"{chapter['status']!r}. Expected 'in_review'."
        )

    get_client().table("chapters").update(
        {
            "notes": notes.strip(),
            "status": "processing",
            "error_message": None,
        }
    ).eq("id", chapter_id).execute()

    log_event(
        "chapter_revision_requested",
        f"Editor submitted revision notes for chapter {chapter['chapter_index']}",
        book_id=chapter["book_id"],
        chapter_id=chapter_id,
    )


def prepare_retry_chapter(chapter_id: str) -> None:
    chapter = _get_chapter(chapter_id)
    _reject_if_processing(chapter["status"], "Chapter generation")
    if chapter["status"] != "error":
        raise ValueError(
            f"Cannot retry chapter: status is {chapter['status']!r}. Expected 'error'."
        )
    get_client().table("chapters").update(
        {"status": "processing", "error_message": None}
    ).eq("id", chapter_id).execute()


# ── final compilation stage ──


def prepare_compilation(book_id: str) -> None:
    book = _get_book(book_id)
    _reject_if_processing(book["final_status"], "Compilation")
    allowed = {"in_review", "error"}
    if book["final_status"] not in allowed:
        raise ValueError(
            f"Cannot compile: final_status is {book['final_status']!r}. "
            f"Expected one of {allowed}. All chapters must be approved first."
        )
    get_client().table("books").update(
        {"final_status": "processing", "error_message": None}
    ).eq("id", book_id).execute()


def execute_compilation(book_id: str) -> None:
    db = get_client()
    try:
        _compile(book_id)
    except Exception as exc:
        logger.exception("Compilation failed for book %s", book_id)
        db.table("books").update(
            {
                "final_status": "error",
                "error_message": str(exc),
            }
        ).eq("id", book_id).execute()
        log_event("compilation_error", str(exc), book_id=book_id)
