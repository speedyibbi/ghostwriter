"""Detect missing or failed chapter summaries."""

SUMMARY_ERROR_PREFIX = "Summary generation failed:"


def is_summary_error(message: str | None) -> bool:
    return bool(message and message.startswith(SUMMARY_ERROR_PREFIX))


def summary_ok(chapter: dict) -> bool:
    """True when an approved chapter has a usable summary and no summary error."""
    if chapter.get("status") != "approved":
        return True
    if is_summary_error(chapter.get("error_message")):
        return False
    return bool((chapter.get("summary") or "").strip())


def summary_warning(chapter: dict) -> str | None:
    """User-facing warning for approved chapters that need summary attention."""
    if chapter.get("status") != "approved" or summary_ok(chapter):
        return None
    msg = chapter.get("error_message")
    if is_summary_error(msg):
        return msg
    return "Summary missing — later chapters may lack narrative context."
