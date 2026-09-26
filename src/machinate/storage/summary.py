"""Derive a document summary from its body.

Summaries are never stored: they are computed from the first prose paragraph so
authors keep a single source of truth (the body itself).
"""

import re
from typing import Final

_HEADING: Final = re.compile(r"^#{1,6}(\s|$)")
_LABEL: Final = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,30}:(\s|$)")
_LINK: Final = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def derive_summary(body: str) -> str | None:
    """Return the first prose paragraph of ``body`` as a single line.

    Leading markdown headings and single-line ``Label:`` preambles (such as
    ``Project: machinate``) are skipped, so a plan body that opens with a title
    heading does not summarise as that heading. Inline emphasis, code ticks, and
    links are stripped. Returns ``None`` when the body has no prose.
    """
    for paragraph in _paragraphs(body):
        lines = [
            line.strip()
            for line in paragraph
            if not _HEADING.match(line.strip()) and not _LABEL.match(line.strip())
        ]
        text = " ".join(lines).strip()
        if text:
            text = _LINK.sub(r"\1", text)
            return text.replace("**", "").replace("__", "").replace("`", "")
    return None


def _paragraphs(body: str) -> list[list[str]]:
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in body.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    return paragraphs
