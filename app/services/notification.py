import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)

_SUBJECTS: dict[str, str] = {
    "outline_ready": "Outline ready for review",
    "chapter_ready": "Chapter ready for review",
    "compilation_done": "Book compilation complete",
    "workflow_error": "Workflow error — action required",
}


def notify(event: str, book_title: str = "", details: str = "") -> None:
    if not settings.smtp_host or not settings.smtp_to:
        logger.debug("SMTP not configured; skipping notification for event %r.", event)
        return

    subject_base = _SUBJECTS.get(event, event.replace("_", " ").title())
    subject = f"[Ghostwriter] {subject_base}"
    if book_title:
        subject += f" — {book_title}"

    body_parts: list[str] = []
    if book_title:
        body_parts += [f"Book: {book_title}", ""]
    if details:
        body_parts.append(details)
    body = "\n".join(body_parts)

    try:
        msg = MIMEMultipart()
        msg["From"] = settings.smtp_user or "ghostwriter"
        msg["To"] = settings.smtp_to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        logger.info("Notification sent: %r", subject)
    except Exception as exc:
        logger.warning("Failed to send notification for event %r: %s", event, exc)
