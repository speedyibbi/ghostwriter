"""
Workflow runner — the central state machine

Each public function corresponds to exactly one editor action (button press in
the UI → API route → function here). Functions validate the current DB state
before doing anything, so they are safe to call from the API layer without
pre-checking.

Raises:
    ValueError   — invalid state transition or missing data (→ HTTP 400)
    LLMError     — LLM call failed after retries (→ HTTP 500)
                   The service layer already persisted the error state before
                   re-raising, so no additional DB cleanup is needed here.
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


# ── outline stage ──


def run_outline_generation(book_id: str) -> None:
    """
    Generate (or retry) the outline for a book.

    Valid from: pending | error
    """
    book = _get_book(book_id)
    allowed = {"pending", "error"}
    if book["outline_status"] not in allowed:
        raise ValueError(
            f"Cannot generate outline: current status is {book['outline_status']!r}. "
            f"Expected one of {allowed}."
        )
    _gen_outline(book_id)


def submit_outline_notes(book_id: str, notes: str) -> None:
    """
    Save the editor's revision notes on the outline and immediately
    regenerate it.

    Valid from: in_review
    """
    if not notes or not notes.strip():
        raise ValueError("Revision notes cannot be empty")

    book = _get_book(book_id)
    if book["outline_status"] != "in_review":
        raise ValueError(
            f"Cannot submit outline notes: current status is "
            f"{book['outline_status']!r}. Expected 'in_review'."
        )

    get_client().table("books").update(
        {
            "notes_after_outline": notes.strip(),
            "outline_status": "needs_revision",
        }
    ).eq("id", book_id).execute()

    log_event(
        "outline_revision_requested", "Editor submitted revision notes", book_id=book_id
    )

    _gen_outline(book_id)


def approve_outline(book_id: str) -> None:
    """
    Approve the outline, create chapter rows by parsing it, then trigger
    generation of the first chapter.

    Valid from: in_review
    Chapter rows are created idempotently (safe to call twice).
    """
    book = _get_book(book_id)
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

    # Create chapter rows (idempotent — skip existing ones).
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

    # Trigger the first chapter immediately.
    first = (
        db.table("chapters")
        .select("id")
        .eq("book_id", book_id)
        .eq("chapter_index", min_index)
        .execute()
    )
    if first.data:
        _gen_chapter(first.data[0]["id"])


# ── chapter stage ──


def approve_chapter(chapter_id: str) -> None:
    """
    Approve a chapter, generate its summary, then either trigger the next
    pending chapter or mark the book ready for final compilation.

    Valid from: in_review
    Summary failure is non-fatal: the chapter stays approved and the workflow
    continues, but the missing summary will reduce LLM context for later chapters.
    """
    chapter = _get_chapter(chapter_id)
    if chapter["status"] != "in_review":
        raise ValueError(
            f"Cannot approve chapter: current status is "
            f"{chapter['status']!r}. Expected 'in_review'."
        )

    book_id = chapter["book_id"]
    db = get_client()

    db.table("chapters").update({"status": "approved"}).eq("id", chapter_id).execute()
    log_event(
        "chapter_approved",
        f"Chapter {chapter['chapter_index']} approved",
        book_id=book_id,
        chapter_id=chapter_id,
    )

    # Generate summary before triggering the next chapter so the context is available immediately.
    try:
        _gen_summary(chapter_id)
    except LLMError as exc:
        logger.warning(
            "Summary generation failed for chapter %s (continuing): %s",
            chapter_id,
            exc,
        )
        db.table("chapters").update(
            {
                "error_message": f"Summary generation failed: {exc}",
            }
        ).eq("id", chapter_id).execute()

    # Trigger the next pending chapter.
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
        _gen_chapter(next_ch.data[0]["id"])
        return

    # No more pending chapters — check whether all chapters are now approved.
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


def submit_chapter_notes(chapter_id: str, notes: str) -> None:
    """
    Save the editor's revision notes on a chapter and immediately regenerate it.

    Valid from: in_review
    """
    if not notes or not notes.strip():
        raise ValueError("Revision notes cannot be empty")

    chapter = _get_chapter(chapter_id)
    if chapter["status"] != "in_review":
        raise ValueError(
            f"Cannot submit chapter notes: current status is "
            f"{chapter['status']!r}. Expected 'in_review'."
        )

    get_client().table("chapters").update(
        {
            "notes": notes.strip(),
            "status": "needs_revision",
        }
    ).eq("id", chapter_id).execute()

    log_event(
        "chapter_revision_requested",
        f"Editor submitted revision notes for chapter {chapter['chapter_index']}",
        book_id=chapter["book_id"],
        chapter_id=chapter_id,
    )

    _gen_chapter(chapter_id)


# ── chapter error recovery ──


def retry_chapter_generation(chapter_id: str) -> None:
    """
    Retry generation for a chapter that is stuck in error state.

    Valid from: error
    """
    chapter = _get_chapter(chapter_id)
    if chapter["status"] != "error":
        raise ValueError(
            f"Cannot retry chapter: status is {chapter['status']!r}. Expected 'error'."
        )
    _gen_chapter(chapter_id)


# ── final compilation stage ──


def run_compilation(book_id: str) -> str:
    """
    Compile all approved chapters into output files.

    Valid from: in_review (final_status)
    Returns the output directory path.
    """
    book = _get_book(book_id)
    if book["final_status"] != "in_review":
        raise ValueError(
            f"Cannot compile: final_status is {book['final_status']!r}. "
            "Expected 'in_review'. All chapters must be approved first."
        )
    return _compile(book_id)
