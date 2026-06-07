"""Recover books and chapters stuck in ``processing``."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.database import get_client
from app.services.log import log_event

logger = logging.getLogger(__name__)

STUCK_MESSAGE = (
    "Job did not finish (cancelled, interrupted, or timed out). You can retry when ready."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _is_stale(updated_at: str | None, cutoff: datetime) -> bool:
    ts = _parse_ts(updated_at)
    if ts is None:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts < cutoff


def sweep_stale_jobs() -> int:
    """
    Mark long-running ``processing`` rows as ``error``.

    Uses ``updated_at`` and ``STALE_JOB_MINUTES`` from settings.
    Returns the number of rows updated. No-op when ``stale_job_minutes <= 0``.
    """
    minutes = settings.stale_job_minutes
    if minutes <= 0:
        return 0

    cutoff = _utc_now() - timedelta(minutes=minutes)
    db = get_client()
    count = 0

    books = (
        db.table("books")
        .select("id, outline_status, final_status, updated_at")
        .execute()
        .data
        or []
    )
    for book in books:
        book_id = book["id"]
        updated_at = book.get("updated_at")
        if book.get("outline_status") == "processing" and _is_stale(
            updated_at, cutoff
        ):
            db.table("books").update(
                {"outline_status": "error", "error_message": STUCK_MESSAGE}
            ).eq("id", book_id).execute()
            log_event("outline_job_stale", STUCK_MESSAGE, book_id=book_id)
            count += 1
            logger.warning("Stale outline job reset for book %s", book_id)

        if book.get("final_status") == "processing" and _is_stale(
            updated_at, cutoff
        ):
            db.table("books").update(
                {"final_status": "error", "error_message": STUCK_MESSAGE}
            ).eq("id", book_id).execute()
            log_event("compilation_job_stale", STUCK_MESSAGE, book_id=book_id)
            count += 1
            logger.warning("Stale compilation job reset for book %s", book_id)

    chapters = (
        db.table("chapters")
        .select("id, book_id, chapter_index, status, updated_at")
        .eq("status", "processing")
        .execute()
        .data
        or []
    )
    for chapter in chapters:
        if not _is_stale(chapter.get("updated_at"), cutoff):
            continue
        chapter_id = chapter["id"]
        db.table("chapters").update(
            {"status": "error", "error_message": STUCK_MESSAGE}
        ).eq("id", chapter_id).execute()
        log_event(
            "chapter_job_stale",
            f"Chapter {chapter['chapter_index']}: {STUCK_MESSAGE}",
            book_id=chapter["book_id"],
            chapter_id=chapter_id,
        )
        count += 1
        logger.warning("Stale chapter job reset for chapter %s", chapter_id)

    if count:
        logger.info("Stale job sweep: reset %d stuck processing row(s)", count)
    return count


def _get_book_refresh(db, book_id: str) -> dict | None:
    resp = db.table("books").select("*").eq("id", book_id).execute()
    return resp.data[0] if resp.data else None


def cancel_outline_job(book_id: str) -> None:
    book = _get_book_refresh(get_client(), book_id)
    if not book:
        raise ValueError(f"Book {book_id!r} not found")
    if book["outline_status"] != "processing":
        raise ValueError(
            f"Cannot cancel outline job: status is {book['outline_status']!r}, "
            "not 'processing'."
        )
    get_client().table("books").update(
        {"outline_status": "error", "error_message": STUCK_MESSAGE}
    ).eq("id", book_id).execute()
    log_event("outline_job_cancelled", STUCK_MESSAGE, book_id=book_id)


def cancel_compilation_job(book_id: str) -> None:
    book = _get_book_refresh(get_client(), book_id)
    if not book:
        raise ValueError(f"Book {book_id!r} not found")
    if book["final_status"] != "processing":
        raise ValueError(
            f"Cannot cancel compilation: final_status is {book['final_status']!r}, "
            "not 'processing'."
        )
    get_client().table("books").update(
        {"final_status": "error", "error_message": STUCK_MESSAGE}
    ).eq("id", book_id).execute()
    log_event("compilation_job_cancelled", STUCK_MESSAGE, book_id=book_id)


def cancel_chapter_job(chapter_id: str) -> None:
    db = get_client()
    resp = db.table("chapters").select("*").eq("id", chapter_id).execute()
    if not resp.data:
        raise ValueError(f"Chapter {chapter_id!r} not found")
    chapter = resp.data[0]
    if chapter["status"] != "processing":
        raise ValueError(
            f"Cannot cancel chapter job: status is {chapter['status']!r}, "
            "not 'processing'."
        )
    db.table("chapters").update(
        {"status": "error", "error_message": STUCK_MESSAGE}
    ).eq("id", chapter_id).execute()
    log_event(
        "chapter_job_cancelled",
        f"Chapter {chapter['chapter_index']}: {STUCK_MESSAGE}",
        book_id=chapter["book_id"],
        chapter_id=chapter_id,
    )
