"""Shared Markdown citation context and explicit publication-year claims."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_BOUNDARY = re.compile(r"^(?:\s*$| {0,3}#{1,6}(?:[ \t]|$))")
_LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
_LINK_LABEL = re.compile(r"^ {0,3}\[(?!\^)((?:\\.|[^\[\]\\]){1,999})\]:[ \t]*(?:\n[ \t]*)?")
_LINK_DESTINATION = r"\((?:[^()\n]|\([^()\n]*\))*\)"
_IMAGE = rf"!\[[^\]\n]*\](?:{_LINK_DESTINATION}|\[[^\]\n]*\])?"
_REFERENCE_LINK = re.compile(r"(?<!\\)\[([^\[\]\n]*)\](?:\[([^\[\]\n]*)\])?")


@dataclass(frozen=True, slots=True)
class ReferenceDefinition:
    """A parsed definition with zero-based source lines and an exclusive end."""

    label: str
    destination: str
    title: str
    start: int
    end: int
    destination_line: int
    title_line: int


def _destination_end(text: str, start: int) -> int | None:
    """Consume an angle destination or balanced, whitespace-free destination."""
    angle = text[start : start + 1] == "<"
    cursor, depth = start + int(angle), 0
    while cursor < len(text):
        char = text[cursor]
        if char == "\\" and cursor + 1 < len(text) and text[cursor + 1] in r"\()<>":
            cursor += 2
            continue
        if angle:
            if char == ">":
                return cursor + 1
            if char in "<\n":
                return None
        elif char.isspace() or ord(char) < 32:
            break
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return None
        cursor += 1
    return cursor if not angle and cursor > start and depth == 0 else None


def _title_end(text: str, start: int) -> int | None:
    """Consume a delimited title; Markdown block markers inside it are text."""
    closing = {'"': '"', "'": "'", "(": ")"}.get(text[start : start + 1])
    if closing is None:
        return None
    cursor = start + 1
    while cursor < len(text):
        char = text[cursor]
        if char == "\\" and cursor + 1 < len(text) and text[cursor + 1] in "\\\"'()":
            cursor += 2
            continue
        if char == closing:
            return cursor + 1
        if closing == ")" and char == "(":
            return None
        if char == "\n" and re.match(r"\n[ \t]*\n", text[cursor:]):
            return None
        cursor += 1
    return None


def reference_definition_at(lines: Sequence[str], index: int) -> ReferenceDefinition | None:
    """Parse a complete definition, preserving multiline labels and titles."""
    if not re.match(r"^ {0,3}\[", lines[index]):
        return None
    text = "\n".join(lines[index:])
    match = _LINK_LABEL.match(text)
    if match is None or not match[1].strip() or re.search(r"\n[ \t]*\n", match[1]):
        return None
    start = match.end()
    end = _destination_end(text, start)
    if end is None:
        return None
    destination = text[start:end]
    destination_line = index + text.count("\n", 0, start)
    tail = end
    while tail < len(text) and text[tail] in " \t":
        tail += 1
    title_line, title = destination_line, ""
    if tail < len(text):
        next_line = text[tail] == "\n"
        title_start = tail
        if next_line:
            title_start += 1
            while title_start < len(text) and text[title_start] in " \t":
                title_start += 1
        title_end = _title_end(text, title_start) if title_start > end else None
        if title_end is not None and re.match(r"[ \t]*(?:\n|$)", text[title_end:]):
            title = text[title_start + 1 : title_end - 1]
            title_line = index + text.count("\n", 0, title_start)
            end = title_end
        elif not next_line:
            return None  # Same-line prose or an invalid title is ordinary text.
    return ReferenceDefinition(
        label=" ".join(match[1].casefold().split()),
        destination=destination[1:-1] if destination.startswith("<") else destination,
        title=title,
        start=index,
        end=index + text.count("\n", 0, end) + 1,
        destination_line=destination_line,
        title_line=title_line,
    )


def reference_definitions(lines: Sequence[str]) -> tuple[ReferenceDefinition, ...]:
    """Index definitions without interpreting text inside their labels or titles."""
    definitions = []
    index = 0
    while index < len(lines):
        definition = reference_definition_at(lines, index)
        if definition is None:
            index += 1
        else:
            definitions.append(definition)
            index = definition.end
    return tuple(definitions)


def reference_definition(line: str, continuation: str = "") -> tuple[str, str, str] | None:
    """Separate a Markdown reference identifier, destination, and optional title."""
    lines = (line + ("\n" + continuation if continuation else "")).splitlines()
    definition = reference_definition_at(lines, 0) if lines else None
    return (definition.label, definition.destination, definition.title) if definition is not None else None


def collect_entry(lines: Sequence[str], doi_idx: int, definitions: tuple[ReferenceDefinition, ...] | None = None) -> str:
    """Collect one item without absorbing adjacent lists or link definitions."""
    definitions = reference_definitions(lines) if definitions is None else definitions
    for definition in definitions:
        if definition.start <= doi_idx < definition.end:
            return " ".join(line.strip() for line in lines[definition.start : definition.end])
    definition_lines = {index for definition in definitions for index in range(definition.start, definition.end)}
    start = doi_idx
    while start > 0 and not _LIST_ITEM.match(lines[start]) and not _BOUNDARY.match(lines[start - 1]):
        if start - 1 in definition_lines:
            break
        start -= 1
    end = doi_idx + 1
    while end < len(lines) and not _BOUNDARY.match(lines[end]) and not _LIST_ITEM.match(lines[end]) and end not in definition_lines:
        end += 1
    return " ".join(line.strip() for line in lines[start:end])


def reference_destinations(line: str, definitions: dict[str, str]) -> list[str]:
    """Resolve reference uses through the same definition bindings as the audit."""
    text = re.sub(_IMAGE, "", line)
    destinations = []
    for match in _REFERENCE_LINK.finditer(text):
        if text[match.end() :].startswith("("):
            continue  # An inline link takes precedence over a shortcut reference.
        label = " ".join((match[2] or match[1]).casefold().split())
        if label in definitions:
            destinations.append(definitions[label])
    return destinations


def publication_years(entry: str, doi: str) -> tuple[str, ...]:
    """Extract stated years while excluding DOI identifiers and URL destinations."""
    text = re.sub(re.escape(doi), "", entry, flags=re.IGNORECASE)
    text = re.sub(r"https?://[^\s<>]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b10\.\d{4,9}/\S+", "", text, flags=re.IGNORECASE)
    return tuple(sorted({match.group() for match in re.finditer(r"\b(?:1[0-9]{3}|2[0-9]{3})\b", text)}))
