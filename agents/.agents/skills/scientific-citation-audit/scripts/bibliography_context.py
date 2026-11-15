"""Shared Markdown citation context and explicit publication-year claims."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_BOUNDARY = re.compile(r"^(?:\s*$| {0,3}#{1,6}(?:[ \t]|$))")
_LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
_LINK_DEFINITION = re.compile(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(?:\n[ \t]*)?(<[^>\n]+>|\S+)([^\n]*)$")


def reference_definition(line: str, continuation: str = "") -> tuple[str, str, str] | None:
    """Separate a Markdown reference identifier, destination, and optional title."""
    match = _LINK_DEFINITION.fullmatch(line)
    if match is None and continuation:
        match = _LINK_DEFINITION.fullmatch(line + "\n" + continuation)
    if match is None:
        return None
    label, destination, title = str(match[1]), str(match[2]), str(match[3])
    return " ".join(label.casefold().split()), destination.removeprefix("<").removesuffix(">"), title.strip()


def reference_definition_at(lines: Sequence[str], index: int) -> tuple[str, str, str] | None:
    """Recognize a definition even when its destination starts on the next line."""
    return reference_definition(lines[index], lines[index + 1] if index + 1 < len(lines) else "")


def _definition_end(lines: Sequence[str], index: int, title: str) -> int:
    """Retain optional quoted titles, including titles continued on later lines."""
    end = index + (1 if reference_definition(lines[index]) is not None else 2)
    delimiters = {'"': '"', "'": "'", "(": ")"}
    if not title and end < len(lines) and lines[end].lstrip()[:1] in delimiters:
        title = lines[end].strip()
        end += 1
    closing = delimiters.get(title[:1])
    if closing is not None:
        while (
            (len(title) == 1 or not title.endswith(closing) or title.endswith("\\" + closing))
            and end < len(lines)
            and not _BOUNDARY.match(lines[end])
            and not _LIST_ITEM.match(lines[end])
            and reference_definition_at(lines, end) is None
        ):
            title += " " + lines[end].strip()
            end += 1
    return end


def collect_entry(lines: Sequence[str], doi_idx: int) -> str:
    """Collect one item without absorbing adjacent lists or link definitions."""
    if (definition := reference_definition_at(lines, doi_idx)) is not None:
        return " ".join(line.strip() for line in lines[doi_idx : _definition_end(lines, doi_idx, definition[2])])
    start = doi_idx
    while start > 0 and not _LIST_ITEM.match(lines[start]) and not _BOUNDARY.match(lines[start - 1]):
        if (definition := reference_definition_at(lines, start - 1)) is not None:
            end = _definition_end(lines, start - 1, definition[2])
            if doi_idx < end:
                return " ".join(line.strip() for line in lines[start - 1 : end])
            start = max(start, end)
            break
        start -= 1
    end = doi_idx + 1
    while end < len(lines) and not _BOUNDARY.match(lines[end]) and not _LIST_ITEM.match(lines[end]) and reference_definition_at(lines, end) is None:
        end += 1
    return " ".join(line.strip() for line in lines[start:end])


def publication_years(entry: str, doi: str) -> tuple[str, ...]:
    """Extract stated years while excluding DOI identifiers and URL destinations."""
    text = re.sub(re.escape(doi), "", entry, flags=re.IGNORECASE)
    text = re.sub(r"https?://[^\s<>]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b10\.\d{4,9}/\S+", "", text, flags=re.IGNORECASE)
    return tuple(sorted({match.group() for match in re.finditer(r"\b(?:1[0-9]{3}|2[0-9]{3})\b", text)}))
