from fastapi import APIRouter

from app.core.database import get_client
from app.services.summary_status import summary_ok, summary_warning

router = APIRouter()


def _enrich_chapter(chapter: dict) -> dict:
    enriched = dict(chapter)
    enriched["summary_ok"] = summary_ok(chapter)
    warning = summary_warning(chapter)
    if warning:
        enriched["summary_warning"] = warning
    return enriched


@router.get("/{book_id}")
def list_chapters(book_id: str):
    """Return all chapters for a book ordered by chapter_index."""
    resp = (
        get_client()
        .table("chapters")
        .select(
            "id, book_id, chapter_index, title, status, "
            "content, summary, notes, revision_count, error_message"
        )
        .eq("book_id", book_id)
        .order("chapter_index")
        .execute()
    )
    return [_enrich_chapter(ch) for ch in (resp.data or [])]
