import logging
import time
from pathlib import Path

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from app.core.config import settings

logger = logging.getLogger(__name__)

# Errors that are safe to retry (rate limits, transient server errors).
_RETRYABLE = (
    google_exceptions.ResourceExhausted,
    google_exceptions.ServiceUnavailable,
    google_exceptions.DeadlineExceeded,
    google_exceptions.InternalServerError,
)

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 2.0  # seconds; doubles on each retry

_PROMPTS_DIR = Path(__file__).parent / "prompts"


class LLMError(Exception):
    pass


_model: genai.GenerativeModel | None = None


def _get_model() -> genai.GenerativeModel:
    global _model
    if _model is None:
        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel(settings.gemini_model)
    return _model


def generate(prompt: str) -> str:
    model = _get_model()
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = model.generate_content(prompt)
            return response.text
        except _RETRYABLE as exc:
            last_exc = exc
            wait = _INITIAL_BACKOFF * (2 ** (attempt - 1))
            logger.warning(
                "Gemini transient error (attempt %d/%d): %s — retrying in %.1fs.",
                attempt,
                _MAX_RETRIES,
                exc,
                wait,
            )
            time.sleep(wait)
        except Exception as exc:
            raise LLMError(f"Gemini call failed: {exc}") from exc

    raise LLMError(
        f"Gemini call failed after {_MAX_RETRIES} retries: {last_exc}"
    ) from last_exc


def load_prompt(name: str, **kwargs: str) -> str:
    """
    Load a prompt template from app/llm/prompts/<name>.txt and substitute
    all keyword arguments using str.format().

    Example:
        prompt = load_prompt("outline", title="My Book", notes_before_outline="...")
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    template = path.read_text(encoding="utf-8")
    return template.format(**kwargs)
