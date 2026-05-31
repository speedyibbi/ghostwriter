"""
Parse chapter headings from LLM-generated outline text.

Supports several common formats, e.g.:
  Chapter 1: Title
  Chapter 2 - Title
  Ch. 3: Title
  ## Chapter 4: Title
"""

import re

_CHAPTER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^Chapter\s+(\d+)\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^Chapter\s+(\d+)\s*[-–—]\s*(.+)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^Ch\.?\s*(\d+)\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^#+\s*Chapter\s+(\d+)\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
)

PARSE_HINT = (
    'Expected lines like "Chapter 1: Title" (also "Chapter 1 - Title" or "Ch. 1: Title").'
)


def parse_chapters(outline: str) -> list[tuple[int, str]]:
    """Return [(chapter_index, title), …] sorted by chapter index."""
    if not outline or not outline.strip():
        return []

    by_index: dict[int, str] = {}
    for pattern in _CHAPTER_PATTERNS:
        for num, title in pattern.findall(outline):
            idx = int(num)
            cleaned = title.strip()
            if idx not in by_index and cleaned:
                by_index[idx] = cleaned

    return sorted(by_index.items())


def outline_parse_error(outline: str | None) -> str | None:
    """Return a user-facing error when *outline* has no parseable chapters, else None."""
    if parse_chapters(outline or ""):
        return None
    return f"No chapters could be parsed from the outline. {PARSE_HINT}"
