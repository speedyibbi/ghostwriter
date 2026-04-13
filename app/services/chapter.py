import logging

from app.core.database import get_client
from app.llm.client import LLMError, generate, load_prompt
from app.services.log import log_event
from app.services.notification import notify

logger = logging.getLogger(__name__)

def generate_chapter(chapter_id: str) -> str:
    """
    Generate content for a single chapter and persist it to the DB.

    Fetches the book outline and all approved prior-chapter summaries to build
    the context block.  Handles both first generation and revisions — if the
    chapter row already has notes, they are injected into the prompt.

    Sets chapter status to 'in_review' on success, 'error' on failure.
    Increments revision_count on every successful generation.
    Raises LLMError so the caller can propagate the error state.
    """
    db = get_client()

    ch_resp = db.table("chapters").select("*").eq("id", chapter_id).execute()
    if not ch_resp.data:
        raise ValueError(f"Chapter {chapter_id!r} not found")
    chapter = ch_resp.data[0]
    book_id = chapter["book_id"]

    bk_resp = db.table("books").select("title, outline").eq("id", book_id).execute()
    if not bk_resp.data:
        raise ValueError(f"Book {book_id!r} not found")
    book = bk_resp.data[0]

    # Aggregate summaries of every approved chapter that comes before this one.
    # These are injected as context so the LLM can maintain narrative continuity.
    prior_resp = (
        db.table("chapters")
        .select("chapter_index, title, summary")
        .eq("book_id", book_id)
        .eq("status", "approved")
        .lt("chapter_index", chapter["chapter_index"])
        .order("chapter_index")
        .execute()
    )
    prior_chapters = prior_resp.data or []

    summaries_block = ""
    if prior_chapters:
        lines = ["Summary of chapters written so far:"]
        for ch in prior_chapters:
            ch_title = ch.get("title") or f"Chapter {ch['chapter_index']}"
            lines.append(f"\nChapter {ch['chapter_index']}: \"{ch_title}\"")
            lines.append((ch.get("summary") or "").strip())
        summaries_block = "\n".join(lines) + "\n\n"

    notes_block = ""
    if chapter.get("notes"):
        notes_block = f"Revision notes from the editor:\n{chapter['notes']}\n\n"

    chapter_title = chapter.get("title") or f"Chapter {chapter['chapter_index']}"

    try:
        prompt = load_prompt(
            "chapter",
            title=book["title"],
            outline=book.get("outline") or "",
            chapter_index=str(chapter["chapter_index"]),
            chapter_title=chapter_title,
            summaries_block=summaries_block,
            notes_block=notes_block,
        )
        content = generate(prompt)
    except LLMError as exc:
        db.table("chapters").update({
            "status": "error",
            "error_message": str(exc),
        }).eq("id", chapter_id).execute()
        log_event("chapter_error", str(exc), book_id=book_id, chapter_id=chapter_id)
        raise

    db.table("chapters").update({
        "content": content,
        "status": "in_review",
        "revision_count": (chapter.get("revision_count") or 0) + 1,
        "error_message": None,
    }).eq("id", chapter_id).execute()

    log_event(
        "chapter_generated",
        f"Chapter {chapter['chapter_index']} generated for \"{book['title']}\"",
        book_id=book_id,
        chapter_id=chapter_id,
    )
    notify(
        "chapter_ready",
        book_title=book["title"],
        details=(
            f"Chapter {chapter['chapter_index']}: \"{chapter_title}\" "
            "is ready for your review in Ghostwriter."
        ),
    )

    return content

def generate_summary(chapter_id: str) -> str:
    """
    Generate a concise summary for an already-written chapter and store it.

    The summary is used as context when generating subsequent chapters.
    Raises LLMError on failure (caller decides whether to treat this as fatal).
    """
    db = get_client()

    ch_resp = (
        db.table("chapters")
        .select("book_id, chapter_index, title, content")
        .eq("id", chapter_id)
        .execute()
    )
    if not ch_resp.data:
        raise ValueError(f"Chapter {chapter_id!r} not found")
    chapter = ch_resp.data[0]
    book_id = chapter["book_id"]

    bk_resp = db.table("books").select("title").eq("id", book_id).execute()
    if not bk_resp.data:
        raise ValueError(f"Book {book_id!r} not found")
    book_title = bk_resp.data[0]["title"]

    chapter_title = chapter.get("title") or f"Chapter {chapter['chapter_index']}"

    try:
        prompt = load_prompt(
            "summary",
            title=book_title,
            chapter_index=str(chapter["chapter_index"]),
            chapter_title=chapter_title,
            content=chapter.get("content") or "",
        )
        summary = generate(prompt)
    except LLMError as exc:
        log_event("summary_error", str(exc), book_id=book_id, chapter_id=chapter_id)
        raise

    db.table("chapters").update({"summary": summary}).eq("id", chapter_id).execute()

    log_event(
        "summary_generated",
        f"Summary generated for chapter {chapter['chapter_index']}",
        book_id=book_id,
        chapter_id=chapter_id,
    )

    return summary
