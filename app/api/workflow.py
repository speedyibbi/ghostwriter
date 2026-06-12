from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.workflow import jobs, recovery, runner

router = APIRouter()

_ACCEPTED = {"accepted": True}


class NotesRequest(BaseModel):
    notes: str


class RecoverRequest(BaseModel):
    action: str  # "cancel" | "retry"


def _accepted(**extra) -> JSONResponse:
    return JSONResponse(status_code=202, content={**_ACCEPTED, **extra})


def _prepare(fn):
    """Run synchronous validation / state updates; map ValueError → 400."""
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Book-level actions ──


@router.post("/{book_id}/generate-outline")
def generate_outline(book_id: str):
    _prepare(lambda: runner.prepare_outline_generation(book_id))
    jobs.enqueue(runner.execute_outline_generation, book_id)
    return _accepted(book_id=book_id)


@router.post("/{book_id}/submit-outline-notes")
def submit_outline_notes(book_id: str, body: NotesRequest):
    _prepare(lambda: runner.prepare_submit_outline_notes(book_id, body.notes))
    jobs.enqueue(runner.execute_outline_generation, book_id)
    return _accepted(book_id=book_id)


@router.post("/{book_id}/approve-outline")
def approve_outline(book_id: str):
    first_chapter_id = _prepare(lambda: runner.prepare_approve_outline(book_id))
    if first_chapter_id:
        jobs.enqueue(runner.execute_chapter_generation, first_chapter_id)
    return _accepted(book_id=book_id)


@router.post("/{book_id}/compile")
def compile_book(book_id: str):
    _prepare(lambda: runner.prepare_compilation(book_id))
    jobs.enqueue(runner.execute_compilation, book_id)
    return _accepted(book_id=book_id)


# ── Chapter-level actions ──


@router.post("/chapter/{chapter_id}/approve")
def approve_chapter(chapter_id: str):
    _prepare(lambda: runner.prepare_approve_chapter(chapter_id))
    jobs.enqueue(runner.execute_continue_after_chapter_approval, chapter_id)
    return _accepted(chapter_id=chapter_id)


@router.post("/chapter/{chapter_id}/submit-notes")
def submit_chapter_notes(chapter_id: str, body: NotesRequest):
    _prepare(lambda: runner.prepare_submit_chapter_notes(chapter_id, body.notes))
    jobs.enqueue(runner.execute_chapter_generation, chapter_id)
    return _accepted(chapter_id=chapter_id)


@router.post("/chapter/{chapter_id}/retry")
def retry_chapter(chapter_id: str):
    _prepare(lambda: runner.prepare_retry_chapter(chapter_id))
    jobs.enqueue(runner.execute_chapter_generation, chapter_id)
    return _accepted(chapter_id=chapter_id)


# ── Stuck job recovery ──


@router.post("/{book_id}/recover-outline")
def recover_outline(book_id: str, body: RecoverRequest):
    action = body.action.strip().lower()
    if action == "cancel":
        _prepare(lambda: recovery.cancel_outline_job(book_id))
        return {"ok": True}
    if action == "retry":
        _prepare(lambda: runner.retry_stuck_outline_job(book_id))
        jobs.enqueue(runner.execute_outline_generation, book_id)
        return _accepted(book_id=book_id)
    raise HTTPException(status_code=400, detail="action must be 'cancel' or 'retry'")


@router.post("/{book_id}/recover-compilation")
def recover_compilation(book_id: str, body: RecoverRequest):
    action = body.action.strip().lower()
    if action == "cancel":
        _prepare(lambda: recovery.cancel_compilation_job(book_id))
        return {"ok": True}
    if action == "retry":
        _prepare(lambda: runner.retry_stuck_compilation_job(book_id))
        jobs.enqueue(runner.execute_compilation, book_id)
        return _accepted(book_id=book_id)
    raise HTTPException(status_code=400, detail="action must be 'cancel' or 'retry'")


@router.post("/chapter/{chapter_id}/recover")
def recover_chapter(chapter_id: str, body: RecoverRequest):
    action = body.action.strip().lower()
    if action == "cancel":
        _prepare(lambda: recovery.cancel_chapter_job(chapter_id))
        return {"ok": True}
    if action == "retry":
        _prepare(lambda: runner.retry_stuck_chapter_job(chapter_id))
        jobs.enqueue(runner.execute_chapter_generation, chapter_id)
        return _accepted(chapter_id=chapter_id)
    raise HTTPException(status_code=400, detail="action must be 'cancel' or 'retry'")


@router.post("/chapter/{chapter_id}/regenerate-summary")
def regenerate_summary(chapter_id: str):
    _prepare(lambda: runner.validate_regenerate_summary(chapter_id))
    runner.execute_regenerate_summary(chapter_id)
    return {"ok": True}
