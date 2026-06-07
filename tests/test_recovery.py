"""Tests for stuck processing recovery."""

from datetime import datetime, timedelta, timezone

import pytest

from app.workflow import recovery, runner
from app.workflow.recovery import STUCK_MESSAGE, sweep_stale_jobs


def test_cancel_outline_job(db):
    db.add_book("b1", outline_status="processing")
    recovery.cancel_outline_job("b1")
    book = db.get_book("b1")
    assert book["outline_status"] == "error"
    assert book["error_message"] == STUCK_MESSAGE


def test_cancel_outline_job_rejects_non_processing(db):
    db.add_book("b1", outline_status="pending")
    with pytest.raises(ValueError, match="not 'processing'"):
        recovery.cancel_outline_job("b1")


def test_retry_stuck_outline_job(db):
    db.add_book("b1", outline_status="processing")
    runner.retry_stuck_outline_job("b1")
    assert db.get_book("b1")["outline_status"] == "processing"


def test_cancel_chapter_job(db):
    db.add_book("b1")
    db.add_chapter("c1", "b1", status="processing")
    recovery.cancel_chapter_job("c1")
    assert db.get_chapter("c1")["status"] == "error"


def test_retry_stuck_chapter_job(db):
    db.add_book("b1")
    db.add_chapter("c1", "b1", status="processing")
    runner.retry_stuck_chapter_job("c1")
    assert db.get_chapter("c1")["status"] == "processing"


def test_sweep_stale_jobs_resets_old_rows(db, monkeypatch):
    monkeypatch.setattr("app.workflow.recovery.settings.stale_job_minutes", 30)
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    db.add_book("b1", outline_status="processing", updated_at=old)
    db.add_book("b2", outline_status="processing", updated_at=datetime.now(timezone.utc).isoformat())
    db.add_book("b3")
    db.add_chapter("c1", "b3", status="processing", updated_at=old)

    count = sweep_stale_jobs()

    assert count == 2
    assert db.get_book("b1")["outline_status"] == "error"
    assert db.get_book("b2")["outline_status"] == "processing"
    assert db.get_chapter("c1")["status"] == "error"


def test_sweep_disabled_when_zero(db, monkeypatch):
    monkeypatch.setattr("app.workflow.recovery.settings.stale_job_minutes", 0)
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    db.add_book("b1", outline_status="processing", updated_at=old)
    assert sweep_stale_jobs() == 0
    assert db.get_book("b1")["outline_status"] == "processing"
