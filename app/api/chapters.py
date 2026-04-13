from fastapi import APIRouter

from app.core.database import get_client

router = APIRouter()

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
    return resp.data or []
