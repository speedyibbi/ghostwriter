import os
import sys
from unittest.mock import MagicMock

# Required before any app import that loads Settings.
os.environ.setdefault("SUPABASE_URL", "http://test")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

# Allow importing app modules without the supabase package installed.
if "supabase" not in sys.modules:
    _supabase = MagicMock()
    _supabase.Client = MagicMock
    _supabase.create_client = MagicMock(return_value=MagicMock())
    sys.modules["supabase"] = _supabase

import pytest

from tests.fake_db import InMemorySupabase


@pytest.fixture(autouse=True)
def no_startup_sweep(monkeypatch):
    monkeypatch.setattr("app.workflow.recovery.sweep_stale_jobs", lambda: 0)


@pytest.fixture
def db(monkeypatch) -> InMemorySupabase:
    """Patch Supabase with an in-memory store for workflow tests."""
    store = InMemorySupabase()
    monkeypatch.setattr("app.workflow.runner.get_client", lambda: store)
    monkeypatch.setattr("app.workflow.recovery.get_client", lambda: store)
    monkeypatch.setattr("app.workflow.runner.log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.workflow.recovery.log_event", lambda *args, **kwargs: None)
    return store
