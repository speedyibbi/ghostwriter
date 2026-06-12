from app.services.summary_status import (
    SUMMARY_ERROR_PREFIX,
    is_summary_error,
    summary_ok,
    summary_warning,
)


def test_is_summary_error():
    assert is_summary_error(f"{SUMMARY_ERROR_PREFIX} timeout")
    assert not is_summary_error("Chapter generation failed")
    assert not is_summary_error(None)


def test_summary_ok_approved_with_summary():
    assert summary_ok({"status": "approved", "summary": "A short recap."})


def test_summary_ok_approved_missing_summary():
    assert not summary_ok({"status": "approved", "summary": ""})


def test_summary_ok_approved_with_summary_error():
    ch = {
        "status": "approved",
        "summary": "partial",
        "error_message": f"{SUMMARY_ERROR_PREFIX} blocked",
    }
    assert not summary_ok(ch)


def test_summary_warning_uses_error_message():
    msg = f"{SUMMARY_ERROR_PREFIX} rate limit"
    ch = {"status": "approved", "error_message": msg}
    assert summary_warning(ch) == msg


def test_summary_warning_missing_summary():
    assert summary_warning({"status": "approved"}) == (
        "Summary missing — later chapters may lack narrative context."
    )
