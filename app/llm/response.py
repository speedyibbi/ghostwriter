"""Extract text from Gemini GenerateContentResponse objects."""

import logging

logger = logging.getLogger(__name__)

_UNSET_BLOCK_REASONS = frozenset(
    {
        "",
        "NONE",
        "BLOCK_REASON_UNSPECIFIED",
        "UNSPECIFIED",
        "0",
    }
)


class LLMError(Exception):
    pass


def _reason_label(reason) -> str:
    if reason is None:
        return "UNKNOWN"
    name = getattr(reason, "name", None)
    if name:
        return str(name)
    return str(reason)


def extract_text(response) -> str:
    """
    Read text from a Gemini ``GenerateContentResponse``.

    Raises LLMError with a clear message for blocked prompts, safety filters,
    empty candidates, or missing text parts.
    """
    feedback = getattr(response, "prompt_feedback", None)
    if feedback:
        block = _reason_label(getattr(feedback, "block_reason", None))
        if block.upper() not in _UNSET_BLOCK_REASONS:
            raise LLMError(
                f"Gemini blocked the prompt ({block.replace('_', ' ').lower()})"
            )

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise LLMError("Gemini returned no response candidates")

    candidate = candidates[0]
    finish = _reason_label(getattr(candidate, "finish_reason", None))

    if finish in {"SAFETY", "RECITATION"}:
        raise LLMError(
            f"Gemini blocked the response ({finish.lower()} filter triggered)"
        )

    content = getattr(candidate, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        if finish == "MAX_TOKENS":
            raise LLMError(
                "Gemini response hit the token limit before producing text"
            )
        raise LLMError(f"Gemini returned no text content (finish_reason={finish})")

    text = "".join(getattr(part, "text", "") or "" for part in parts).strip()
    if not text:
        raise LLMError(f"Gemini returned empty text (finish_reason={finish})")

    if finish == "MAX_TOKENS":
        logger.warning("Gemini response truncated (MAX_TOKENS); using partial output")

    return text
