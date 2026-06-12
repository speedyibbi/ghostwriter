"""Workflow HTTP layer: 202 responses and validation errors."""

import pytest
from fastapi.testclient import TestClient

from tests.fake_db import InMemorySupabase


@pytest.fixture
def client(db: InMemorySupabase, monkeypatch) -> TestClient:
    monkeypatch.setattr("app.api.workflow.jobs.enqueue", lambda fn, *args, **kwargs: None)
    from main import app

    return TestClient(app)


def test_generate_outline_returns_202(client, db):
    db.add_book("b1", outline_status="pending")
    res = client.post("/api/workflow/b1/generate-outline")
    assert res.status_code == 202
    assert res.json()["accepted"] is True
    assert db.get_book("b1")["outline_status"] == "processing"


def test_generate_outline_validation_error(client, db):
    db.add_book("b1", outline_status="in_review", outline="Chapter 1: X")
    res = client.post("/api/workflow/b1/generate-outline")
    assert res.status_code == 400
    assert "Cannot generate outline" in res.json()["detail"]


def test_submit_outline_notes_returns_202(client, db):
    db.add_book("b1", outline_status="in_review", outline="Chapter 1: X")
    res = client.post(
        "/api/workflow/b1/submit-outline-notes",
        json={"notes": "More detail please"},
    )
    assert res.status_code == 202
    assert db.get_book("b1")["outline_status"] == "processing"


def test_api_key_required_when_configured(db, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.api_key", "secret")
    monkeypatch.setattr("app.api.workflow.jobs.enqueue", lambda *a, **k: None)
    from main import app

    client = TestClient(app)
    db.add_book("b1", outline_status="pending")

    denied = client.post("/api/workflow/b1/generate-outline")
    assert denied.status_code == 401

    ok = client.post(
        "/api/workflow/b1/generate-outline",
        headers={"X-API-Key": "secret"},
    )
    assert ok.status_code == 202


def test_config_endpoint_public():
    from main import app

    client = TestClient(app)
    res = client.get("/config")
    assert res.status_code == 200
    assert "api_key_required" in res.json()


def test_recover_outline_cancel(client, db):
    db.add_book("b1", outline_status="processing")
    res = client.post("/api/workflow/b1/recover-outline", json={"action": "cancel"})
    assert res.status_code == 200
    assert db.get_book("b1")["outline_status"] == "error"


def test_recover_outline_retry(client, db):
    db.add_book("b1", outline_status="processing")
    res = client.post("/api/workflow/b1/recover-outline", json={"action": "retry"})
    assert res.status_code == 202
    assert db.get_book("b1")["outline_status"] == "processing"


def test_regenerate_summary(client, db, monkeypatch):
    db.add_book("b1")
    db.add_chapter(
        "c1",
        "b1",
        status="approved",
        content="Text",
        error_message="Summary generation failed: old",
    )
    monkeypatch.setattr(
        "app.workflow.runner.execute_regenerate_summary",
        lambda _id: db.chapters["c1"].update(
            {"summary": "Done", "error_message": None}
        ),
    )
    res = client.post("/api/workflow/chapter/c1/regenerate-summary")
    assert res.status_code == 200
    assert res.json()["ok"] is True
