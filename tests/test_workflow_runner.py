import pytest

from app.workflow import runner

OUTLINE_OK = "Chapter 1: Alpha\n\nChapter 2: Beta\n"


# ── outline generation ──


def test_prepare_outline_generation_from_pending(db):
    db.add_book("b1", outline_status="pending")
    runner.prepare_outline_generation("b1")
    assert db.get_book("b1")["outline_status"] == "processing"


def test_prepare_outline_generation_from_error(db):
    db.add_book("b1", outline_status="error", error_message="old")
    runner.prepare_outline_generation("b1")
    assert db.get_book("b1")["outline_status"] == "processing"
    assert db.get_book("b1")["error_message"] is None


def test_prepare_outline_generation_rejects_in_review(db):
    db.add_book("b1", outline_status="in_review", outline=OUTLINE_OK)
    with pytest.raises(ValueError, match="Cannot generate outline"):
        runner.prepare_outline_generation("b1")


def test_prepare_outline_generation_rejects_processing(db):
    db.add_book("b1", outline_status="processing")
    with pytest.raises(ValueError, match="already in progress"):
        runner.prepare_outline_generation("b1")


def test_prepare_outline_generation_book_not_found(db):
    with pytest.raises(ValueError, match="not found"):
        runner.prepare_outline_generation("missing")


# ── outline notes ──


def test_prepare_submit_outline_notes(db):
    db.add_book("b1", outline_status="in_review", outline=OUTLINE_OK)
    runner.prepare_submit_outline_notes("b1", "  Add a chapter on ethics  ")
    book = db.get_book("b1")
    assert book["outline_status"] == "processing"
    assert book["notes_after_outline"] == "Add a chapter on ethics"


def test_prepare_submit_outline_notes_from_error(db):
    db.add_book("b1", outline_status="error", outline="bad format")
    runner.prepare_submit_outline_notes("b1", "Use Chapter N: Title format")
    assert db.get_book("b1")["outline_status"] == "processing"


def test_prepare_submit_outline_notes_empty(db):
    db.add_book("b1", outline_status="in_review")
    with pytest.raises(ValueError, match="cannot be empty"):
        runner.prepare_submit_outline_notes("b1", "   ")


def test_prepare_submit_outline_notes_wrong_status(db):
    db.add_book("b1", outline_status="pending")
    with pytest.raises(ValueError, match="Expected 'in_review' or 'error'"):
        runner.prepare_submit_outline_notes("b1", "notes")


# ── approve outline ──


def test_prepare_approve_outline_creates_chapters(db):
    db.add_book("b1", outline_status="in_review", outline=OUTLINE_OK)
    first_id = runner.prepare_approve_outline("b1")
    assert first_id is not None
    book = db.get_book("b1")
    assert book["outline_status"] == "approved"
    chapters = list(db.chapters.values())
    assert len(chapters) == 2
    assert db.get_chapter(first_id)["status"] == "processing"


def test_prepare_approve_outline_rejects_unparseable(db):
    db.add_book("b1", outline_status="in_review", outline="No chapters here")
    with pytest.raises(ValueError, match="No chapters could be parsed"):
        runner.prepare_approve_outline("b1")


def test_prepare_approve_outline_rejects_wrong_status(db):
    db.add_book("b1", outline_status="pending")
    with pytest.raises(ValueError, match="Expected 'in_review'"):
        runner.prepare_approve_outline("b1")


# ── chapters ──


def test_prepare_approve_chapter(db):
    db.add_book("b1", outline_status="approved")
    db.add_chapter("c1", "b1", status="in_review", chapter_index=1)
    runner.prepare_approve_chapter("c1")
    assert db.get_chapter("c1")["status"] == "approved"


def test_prepare_approve_chapter_rejects_pending(db):
    db.add_book("b1")
    db.add_chapter("c1", "b1", status="pending")
    with pytest.raises(ValueError, match="Expected 'in_review'"):
        runner.prepare_approve_chapter("c1")


def test_prepare_submit_chapter_notes(db):
    db.add_book("b1")
    db.add_chapter("c1", "b1", status="in_review")
    runner.prepare_submit_chapter_notes("c1", "Expand the intro")
    ch = db.get_chapter("c1")
    assert ch["status"] == "processing"
    assert ch["notes"] == "Expand the intro"


def test_prepare_retry_chapter(db):
    db.add_book("b1")
    db.add_chapter("c1", "b1", status="error", error_message="fail")
    runner.prepare_retry_chapter("c1")
    ch = db.get_chapter("c1")
    assert ch["status"] == "processing"
    assert ch["error_message"] is None


def test_prepare_retry_chapter_rejects_in_review(db):
    db.add_book("b1")
    db.add_chapter("c1", "b1", status="in_review")
    with pytest.raises(ValueError, match="Expected 'error'"):
        runner.prepare_retry_chapter("c1")


# ── compilation ──


def test_prepare_compilation(db):
    db.add_book("b1", final_status="in_review")
    runner.prepare_compilation("b1")
    assert db.get_book("b1")["final_status"] == "processing"


def test_prepare_compilation_from_error(db):
    db.add_book("b1", final_status="error", error_message="disk full")
    runner.prepare_compilation("b1")
    assert db.get_book("b1")["final_status"] == "processing"


def test_prepare_compilation_rejects_pending(db):
    db.add_book("b1", final_status="pending")
    with pytest.raises(ValueError, match="Expected one of"):
        runner.prepare_compilation("b1")


def test_validate_regenerate_summary_requires_approved(db):
    db.add_book("b1")
    db.add_chapter("c1", "b1", status="in_review", content="Body")
    with pytest.raises(ValueError, match="Expected 'approved'"):
        runner.validate_regenerate_summary("c1")


def test_validate_regenerate_summary_requires_content(db):
    db.add_book("b1")
    db.add_chapter("c1", "b1", status="approved", content="")
    with pytest.raises(ValueError, match="no content"):
        runner.validate_regenerate_summary("c1")


def test_execute_regenerate_summary_clears_error_on_success(db, monkeypatch):
    db.add_book("b1")
    db.add_chapter(
        "c1",
        "b1",
        status="approved",
        content="Chapter body",
        error_message="Summary generation failed: old",
    )

    def fake_summary(chapter_id: str) -> str:
        db.chapters[chapter_id]["summary"] = "New summary"
        db.chapters[chapter_id]["error_message"] = None
        return "New summary"

    monkeypatch.setattr(
        "app.services.chapter.generate_summary",
        fake_summary,
    )
    runner.execute_regenerate_summary("c1")
    ch = db.get_chapter("c1")
    assert ch["summary"] == "New summary"
    assert ch["error_message"] is None


def test_execute_regenerate_summary_persists_error(db, monkeypatch):
    from app.llm.response import LLMError

    db.add_book("b1")
    db.add_chapter("c1", "b1", status="approved", content="Chapter body")

    def fail_summary(_chapter_id: str) -> str:
        raise LLMError("blocked")

    monkeypatch.setattr("app.services.chapter.generate_summary", fail_summary)
    runner.execute_regenerate_summary("c1")
    assert "Summary generation failed" in db.get_chapter("c1")["error_message"]
