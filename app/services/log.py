import logging

from app.core.database import get_client

logger = logging.getLogger(__name__)


def log_event(
    event: str,
    message: str = "",
    *,
    book_id: str | None = None,
    chapter_id: str | None = None,
) -> None:
    try:
        get_client().table("logs").insert(
            {
                "book_id": book_id,
                "chapter_id": chapter_id,
                "event": event,
                "message": message,
            }
        ).execute()
    except Exception as exc:
        logger.warning("Failed to write log event %r: %s", event, exc)
