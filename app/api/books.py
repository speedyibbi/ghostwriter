from fastapi import APIRouter, HTTPException

from app.core.database import get_client
from app.workflow.outline_parse import parse_chapters

router = APIRouter()


def _with_outline_parse_meta(book: dict) -> dict:
    outline = book.get("outline") or ""
    parsed = parse_chapters(outline)
    book["outline_chapters"] = [
        {"chapter_index": idx, "title": title} for idx, title in parsed
    ]
    book["outline_parse_ok"] = bool(parsed)
    return book


@router.get("/")
def list_books():
    """Return all books ordered by creation date (newest first)."""
    resp = (
        get_client()
        .table("books")
        .select("id, title, outline_status, final_status, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


@router.get("/{book_id}")
def get_book(book_id: str):
    """Return full details for a single book."""
    resp = get_client().table("books").select("*").eq("id", book_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail=f"Book {book_id!r} not found")
    return _with_outline_parse_meta(resp.data[0])
