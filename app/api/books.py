from fastapi import APIRouter, HTTPException

from app.core.database import get_client

router = APIRouter()

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
    return resp.data[0]
