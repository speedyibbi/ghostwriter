from types import SimpleNamespace

import pytest

from app.llm.response import LLMError, extract_text
from app.workflow.outline_parse import outline_parse_error, parse_chapters


# ── outline_parse ──


OUTLINE_STANDARD = """\
Chapter 1: The Beginning
Intro content here.

Chapter 2: The Middle
More content.
"""


def test_parse_chapters_standard_format():
    assert parse_chapters(OUTLINE_STANDARD) == [
        (1, "The Beginning"),
        (2, "The Middle"),
    ]


def test_parse_chapters_dash_and_abbreviation():
    text = "Chapter 1 - First\n\nCh. 2: Second"
    assert parse_chapters(text) == [(1, "First"), (2, "Second")]


def test_parse_chapters_markdown_heading():
    text = "## Chapter 3: Deep Dive"
    assert parse_chapters(text) == [(3, "Deep Dive")]


def test_parse_chapters_empty():
    assert parse_chapters("") == []
    assert outline_parse_error("") is not None


def test_outline_parse_error_ok():
    assert outline_parse_error(OUTLINE_STANDARD) is None


# ── extract_text ──


def _response(*, candidates=None, block_reason=None):
    feedback = (
        SimpleNamespace(block_reason=block_reason) if block_reason is not None else None
    )
    return SimpleNamespace(prompt_feedback=feedback, candidates=candidates or [])


def test_extract_text_happy_path():
    response = _response(
        candidates=[
            SimpleNamespace(
                finish_reason=SimpleNamespace(name="STOP"),
                content=SimpleNamespace(parts=[SimpleNamespace(text="Hello world")]),
            )
        ]
    )
    assert extract_text(response) == "Hello world"


def test_extract_text_no_candidates():
    with pytest.raises(LLMError, match="no response candidates"):
        extract_text(_response())


def test_extract_text_safety_block():
    response = _response(
        candidates=[
            SimpleNamespace(
                finish_reason=SimpleNamespace(name="SAFETY"),
                content=SimpleNamespace(parts=[]),
            )
        ]
    )
    with pytest.raises(LLMError, match="safety filter"):
        extract_text(response)


def test_extract_text_prompt_blocked():
    response = _response(block_reason=SimpleNamespace(name="SAFETY"))
    with pytest.raises(LLMError, match="blocked the prompt"):
        extract_text(response)


def test_extract_text_empty_parts():
    response = _response(
        candidates=[
            SimpleNamespace(
                finish_reason=SimpleNamespace(name="STOP"),
                content=SimpleNamespace(parts=[]),
            )
        ]
    )
    with pytest.raises(LLMError, match="no text content"):
        extract_text(response)
