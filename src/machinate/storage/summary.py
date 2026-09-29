"""Derive a document summary from its body.

Summaries are never stored: they are computed from the first prose paragraph so
authors keep a single source of truth (the body itself).
"""

import re
from typing import Final

_HEADING: Final = re.compile(r"^#{1,6}(\s|$)")
_LABEL: Final = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,30}:(\s|$)")
_FENCE: Final = re.compile(r"^\s*(```|~~~)")
_LINK: Final = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def derive_summary(body: str) -> str | None:
    """Return the first prose paragraph of ``body`` as a single line.

    Fenced code blocks are excluded, and only the leading run of markdown
    headings and single-line ``Label:`` preambles (such as ``Project: machinate``)
    is skipped, so a plan body that opens with a title heading does not summarise
    as that heading while a later ``Label:`` line stays prose. Inline emphasis,
    code ticks, and links are stripped. Returns ``None`` when the body has no prose.
    """
    paragraphs = _paragraphs(_without_fences(body))
    first_label_paragraph: list[str] | None = None
    for paragraph in paragraphs:
        remaining = _strip_leading(paragraph)
        if remaining:
            return _clean(" ".join(remaining))
        if first_label_paragraph is None and any(_LABEL.match(line.strip()) for line in paragraph):
            first_label_paragraph = paragraph
    if first_label_paragraph is not None:
        # The whole body is a single label preamble (e.g. a lone ``TODO: ...``).
        labels = [line.strip() for line in first_label_paragraph if _LABEL.match(line.strip())]
        return _clean(" ".join(labels))
    return None


def _strip_leading(lines: list[str]) -> list[str]:
    """Drop leading heading/label lines, keeping everything from the first prose line."""
    remaining: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not remaining and (_HEADING.match(stripped) or _LABEL.match(stripped)):
            continue
        remaining.append(line)
    return remaining


def _clean(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    return text.replace("**", "").replace("__", "").replace("`", "")


def _without_fences(body: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return "\n".join(lines)


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
