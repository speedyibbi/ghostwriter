import logging

from app.core.database import get_client
from app.llm.client import LLMError, generate, load_prompt
from app.services.log import log_event
from app.services.notification import notify

logger = logging.getLogger(__name__)


def generate_outline(book_id: str) -> str:
    """
    Generate a book outline using the LLM and persist it to the DB.

    Sets outline_status to 'in_review' on success, 'error' on failure.
    Raises LLMError (or ValueError for missing data) so the caller can handle
    the error state at the workflow level.
    """
    db = get_client()

    response = (
        db.table("books")
        .select("title, notes_before_outline")
        .eq("id", book_id)
        .execute()
    )

    if not response.data:
        raise ValueError(f"Book {book_id!r} not found")

    book = response.data[0]

    try:
        prompt = load_prompt(
            "outline",
            title=book["title"],
            notes_before_outline=book["notes_before_outline"],
        )
        outline = generate(prompt)
    except LLMError as exc:
        db.table("books").update(
            {
                "outline_status": "error",
                "error_message": str(exc),
            }
        ).eq("id", book_id).execute()
        log_event("outline_error", str(exc), book_id=book_id)
        raise

    db.table("books").update(
        {
            "outline": outline,
            "outline_status": "in_review",
            "error_message": None,
        }
    ).eq("id", book_id).execute()

    log_event(
        "outline_generated",
        f'Outline generated for "{book["title"]}"',
        book_id=book_id,
    )
    notify(
        "outline_ready",
        book_title=book["title"],
        details="The outline is ready for your review in Ghostwriter.",
    )

    return outline
