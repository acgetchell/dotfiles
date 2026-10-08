"""Shared Markdown citation context and explicit publication-year claims."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_BOUNDARY = re.compile(r"^(?:\s*$| {0,3}#{1,6}(?:[ \t]|$))")
_LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")


def collect_entry(lines: Sequence[str], doi_idx: int) -> str:
    """Collect one bibliography item without absorbing adjacent list entries."""
    start = doi_idx
    while start > 0 and not _LIST_ITEM.match(lines[start]) and not _BOUNDARY.match(lines[start - 1]):
        start -= 1
    end = doi_idx + 1
    while end < len(lines) and not _BOUNDARY.match(lines[end]) and not _LIST_ITEM.match(lines[end]):
        end += 1
    return " ".join(line.strip() for line in lines[start:end])


def publication_years(entry: str, doi: str) -> tuple[str, ...]:
    """Extract stated years while excluding DOI identifiers and URL destinations."""
    text = re.sub(re.escape(doi), "", entry, flags=re.IGNORECASE)
    text = re.sub(r"https?://[^\s<>]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b10\.\d{4,9}/\S+", "", text, flags=re.IGNORECASE)
    return tuple(sorted({match.group() for match in re.finditer(r"\b(?:1[0-9]{3}|2[0-9]{3})\b", text)}))
