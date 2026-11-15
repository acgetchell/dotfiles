"""Shared Markdown citation context and explicit publication-year claims."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_BOUNDARY = re.compile(r"^(?:\s*$| {0,3}#{1,6}(?:[ \t]|$))")
_LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
_LINK_LABEL = re.compile(r"^ {0,3}\[(?!\^)((?:\\.|[^\[\]\\]){1,999})\]:[ \t]*(?:\n[ \t]*)?")


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


@dataclass(frozen=True, slots=True)
class ReferenceUse:
    """A resolved reference use anchored to its opening source line."""

    destination: str
    line: int


@dataclass(frozen=True, slots=True)
class CitationClaims:
    """Visible identity and pointer text derived from retained source context."""

    text: str


@dataclass(frozen=True, slots=True)
class _LinkMatch:
    start: int
    end: int
    text: str
    label: str | None
    image: bool


@dataclass(slots=True)
class _OpenBracket:
    start: int
    image: bool
    active: bool = True


def _angle_destination_end(text: str, start: int) -> int | None:
    for index in range(start + 1, len(text)):
        if text[index] in "<>\\" and _escaped(text, index):
            continue
        if text[index] == ">":
            return index + 1
        if text[index] in "<\n":
            return None
    return None


def _destination_end(text: str, start: int, *, inline: bool = False) -> int | None:
    """Consume an angle destination or balanced, whitespace-free destination."""
    if text[start : start + 1] == "<":
        return _angle_destination_end(text, start)
    cursor, depth = start, 0
    while cursor < len(text):
        char = text[cursor]
        if char == "\\" and cursor + 1 < len(text) and text[cursor + 1] in r"\()<>":
            cursor += 2
            continue
        if char.isspace() or ord(char) < 32:
            break
        if char == "(":
            depth += 1
        elif char == ")":
            if inline and depth == 0:
                break
            depth -= 1
            if depth < 0:
                return None
        cursor += 1
    return cursor if cursor > start and depth == 0 else None


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


def _escaped(text: str, index: int) -> bool:
    start = index
    while start > 0 and text[start - 1] == "\\":
        start -= 1
    return (index - start) % 2 == 1


def _block_boundary_at(text: str, newline: int) -> bool:
    line = text[newline + 1 :].partition("\n")[0]
    return bool(_BOUNDARY.match(line) or _LIST_ITEM.match(line))


def _code_span_end(text: str, start: int) -> int:
    """Consume matching backtick runs, or just an unmatched opening run."""
    opening_end = start + 1
    while text[opening_end : opening_end + 1] == "`":
        opening_end += 1
    for closing in re.finditer(r"`+", text[opening_end:]):
        if any(_block_boundary_at(text, index) for index in range(opening_end, opening_end + closing.start()) if text[index] == "\n"):
            break
        if len(closing.group()) == opening_end - start:
            return opening_end + closing.end()
    return opening_end


def _label_end(text: str, start: int) -> int | None:
    """A reference label ends at its first unescaped closing bracket."""
    for index in range(start + 1, len(text)):
        if text[index] in "[]" and _escaped(text, index):
            continue
        if text[index] == "[":
            return None
        if text[index] == "]":
            return index + 1
        if text[index] == "\n" and _block_boundary_at(text, index):
            return None
    return None


def _label(text: str) -> str | None:
    if not 1 <= len(text) <= 999 or not text.strip():
        return None
    if any(char in "[]" and not _escaped(text, index) for index, char in enumerate(text)):
        return None
    return " ".join(text.casefold().split())


def _inline_end(text: str, start: int) -> int | None:
    """Recognize inline-link precedence only for a valid destination and title."""
    if text[start : start + 1] != "(":
        return None
    cursor = start + 1
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if text[cursor : cursor + 1] == ")":
        return None if re.search(r"\n[ \t]*\n", text[start:cursor]) else cursor + 1
    end = _destination_end(text, cursor, inline=True)
    if end is None:
        return None
    cursor = end
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if text[cursor : cursor + 1] != ")":
        title_end = _title_end(text, cursor) if cursor > end else None
        if title_end is None:
            return None
        cursor = title_end
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
    if text[cursor : cursor + 1] != ")" or re.search(r"\n[ \t]*\n", text[start:cursor]):
        return None
    return cursor + 1


def _reference_candidate(text: str, start: int, end: int) -> tuple[str | None, int, int]:
    """Select a reference label, match end, and fallback cursor for unresolved forms."""
    label = _label(text[start + 1 : end - 1])
    match_end, cursor = end, start + 1
    if text[end : end + 1] == "[" and (label_end := _label_end(text, end)) is not None:
        raw_label = text[end + 1 : label_end - 1]
        explicit = _label(raw_label) if raw_label else label
        if raw_label == "" or explicit is not None:
            label, match_end = explicit, label_end
            cursor = end  # An unresolved full form may start a later full form.
    return label, match_end, cursor


def _close_link(text: str, opening: _OpenBracket, end: int, definitions: dict[str, str]) -> _LinkMatch | None:
    if not opening.active:
        return None
    label = None
    match_end = _inline_end(text, end)
    if match_end is None:
        label, match_end, _fallback = _reference_candidate(text, opening.start, end)
        if label not in definitions:
            return None
    return _LinkMatch(opening.start - int(opening.image), match_end, text[opening.start + 1 : end - 1], label, opening.image)


def _deactivate_outer_links(stack: list[_OpenBracket]) -> None:
    """A nested link disables outer links until its containing image boundary."""
    for opening in reversed(stack):
        if opening.image:
            break
        opening.active = False


def _link_matches(text: str, definitions: dict[str, str]) -> list[_LinkMatch]:
    """Parse inline structure in source order, skipping consumed code and targets."""
    matches = []
    stack: list[_OpenBracket] = []
    cursor = 0
    while cursor < len(text):
        char = text[cursor]
        if char == "\\" and text[cursor + 1 : cursor + 2] in "\\`[]!" and cursor + 1 < len(text):
            cursor += 2
            continue
        if char == "`":
            cursor = _code_span_end(text, cursor)
            continue
        if text[cursor : cursor + 2] == "![":
            stack.append(_OpenBracket(cursor + 1, image=True))
            cursor += 2
            continue
        if char == "[":
            stack.append(_OpenBracket(cursor, image=False))
        elif char == "]" and stack:
            match = _close_link(text, stack.pop(), cursor + 1, definitions)
            if match is not None:
                matches.append(match)
                cursor = match.end
                if not match.image:
                    _deactivate_outer_links(stack)
                continue
        elif char == "\n" and _block_boundary_at(text, cursor):
            stack.clear()
        cursor += 1
    return matches


def _reference_matches(text: str, definitions: dict[str, str]) -> list[_LinkMatch]:
    """Keep resolved references outside image descriptions in source order."""
    matches = _link_matches(text, definitions)
    images = [match for match in matches if match.image]
    return sorted(
        (match for match in matches if match.label is not None and not match.image and not any(image.start <= match.start < image.end for image in images)),
        key=lambda match: match.start,
    )


def _definition_destinations(parsed: tuple[ReferenceDefinition, ...]) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for definition in parsed:
        definitions.setdefault(definition.label, definition.destination)
    return definitions


def mask_images(text: str, parsed: tuple[ReferenceDefinition, ...] = (), *, include_links: bool = False) -> str:
    """Exclude balanced image descriptions while retaining source offsets."""
    matches = _link_matches(text, _definition_destinations(parsed))
    images = [match for match in matches if match.image]
    spans = [(image.start, image.end) for image in images]
    if include_links:
        spans.extend((match.start, match.end) for match in matches if not match.image and any(match.text == text[image.start : image.end] for image in images))
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + re.sub(r"[^\n]", " ", text[start:end]) + text[end:]
    return text


def reference_uses(lines: Sequence[str], parsed: tuple[ReferenceDefinition, ...]) -> tuple[ReferenceUse, ...]:
    """Resolve uses across lines while retaining their original source locations."""
    definitions = _definition_destinations(parsed)
    definition_lines = {index for definition in parsed for index in range(definition.start, definition.end)}
    text = "\n".join(" " * len(line) if index in definition_lines else line for index, line in enumerate(lines))
    return tuple(
        ReferenceUse(definitions[match.label], text.count("\n", 0, match.start)) for match in _reference_matches(text, definitions) if match.label is not None
    )


def collect_claims(lines: Sequence[str], doi_idx: int, parsed: tuple[ReferenceDefinition, ...]) -> CitationClaims:
    """Derive citation claims separately from raw source and hidden identifiers."""
    for definition in parsed:
        if definition.start <= doi_idx < definition.end:
            return CitationClaims(definition.title)
    text = mask_images(collect_entry(lines, doi_idx, parsed), parsed, include_links=True)
    for match in reversed(_reference_matches(text, _definition_destinations(parsed))):
        visible = text[match.start + 1 : match.start + 1 + len(match.text)]
        text = text[: match.start] + visible + text[match.end :]
    return CitationClaims(text)


def publication_years(entry: str, doi: str) -> tuple[str, ...]:
    """Extract stated years while excluding DOI identifiers and URL destinations."""
    text = re.sub(re.escape(doi), "", entry, flags=re.IGNORECASE)
    text = re.sub(r"https?://[^\s<>]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b10\.\d{4,9}/\S+", "", text, flags=re.IGNORECASE)
    return tuple(sorted({match.group() for match in re.finditer(r"\b(?:1[0-9]{3}|2[0-9]{3})\b", text)}))
