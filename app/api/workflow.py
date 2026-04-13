from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.llm.client import LLMError
from app.workflow import runner

router = APIRouter()

class NotesRequest(BaseModel):
    notes: str

def _run(fn):
    """
    Execute *fn*, mapping known exceptions to appropriate HTTP errors.

    ValueError  → 400  (bad state transition or missing data)
    LLMError    → 500  (Gemini call failed; service already persisted error state)
    Exception   → 500  (unexpected)
    """
    try:
        result = fn()
        return result if result is not None else {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}")

# ── Book-level actions ──

@router.post("/{book_id}/generate-outline")
def generate_outline(book_id: str):
    return _run(lambda: runner.run_outline_generation(book_id))

@router.post("/{book_id}/submit-outline-notes")
def submit_outline_notes(book_id: str, body: NotesRequest):
    return _run(lambda: runner.submit_outline_notes(book_id, body.notes))

@router.post("/{book_id}/approve-outline")
def approve_outline(book_id: str):
    return _run(lambda: runner.approve_outline(book_id))

@router.post("/{book_id}/compile")
def compile_book(book_id: str):
    return _run(lambda: {"output_path": runner.run_compilation(book_id)})

# ── Chapter-level actions ──

@router.post("/chapter/{chapter_id}/approve")
def approve_chapter(chapter_id: str):
    return _run(lambda: runner.approve_chapter(chapter_id))

@router.post("/chapter/{chapter_id}/submit-notes")
def submit_chapter_notes(chapter_id: str, body: NotesRequest):
    return _run(lambda: runner.submit_chapter_notes(chapter_id, body.notes))

@router.post("/chapter/{chapter_id}/retry")
def retry_chapter(chapter_id: str):
    return _run(lambda: runner.retry_chapter_generation(chapter_id))
