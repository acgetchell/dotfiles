"""Budgeted lexical source navigation, never semantic inspection evidence."""

import json
import re
from bisect import bisect_right
from itertools import zip_longest
from pathlib import PurePosixPath
from typing import Any

_RUST_TOKENS = re.compile(r"//[^\n]*|/\*|(?:br|cr|r)(?P<hashes>\#*)\".*?\"(?P=hashes)|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\\n])'", re.DOTALL)
_RUST_BLOCK_DELIMITERS = re.compile(r"/\*|\*/")
_RUST_DECLARATION = re.compile(
    r"^[ \t]*(?:pub(?:\([^\n)]*\))?[ \t]+)?(?:(?:async|unsafe|const|default|extern)[ \t]+)*"
    r"(?P<kind>fn|struct|enum|trait|type|impl)\b",
    re.MULTILINE,
)


def _rust_code(text: str) -> str:
    """Mask comments and string literals while retaining source offsets."""
    result = list(text)
    position = 0
    while match := _RUST_TOKENS.search(text, position):
        end = match.end()
        if match.group() == "/*":
            depth = 1
            while depth and (token := _RUST_BLOCK_DELIMITERS.search(text, end)):
                depth += 1 if token.group() == "/*" else -1
                end = token.end()
            if depth:
                end = len(text)
        for index in range(match.start(), end):
            if text[index] not in "\r\n":
                result[index] = " "
        position = end
    return "".join(result)


def _rust_declaration_end(code: str, start: int, end: int) -> int | None:
    """Locate a top-level terminator in an already masked signature window."""
    closers = {"(": ")", "[": "]", "<": ">", "{": "}"}
    nesting: list[str] = []
    array_lengths: set[int] = set()
    for position in range(start, end):
        character = code[position]
        if character in ";{" and not nesting:
            return position + 1
        if character == ";" and nesting[-1:] == ["]"]:
            array_lengths.add(len(nesting))
        # Braces and array lengths already enclose their constant expressions;
        # their shifts/comparisons and function arrows are not type delimiters.
        if character in "<>" and (array_lengths or "}" in nesting or (character == ">" and code[position - 1] == "-")):
            continue
        if character in closers:
            nesting.append(closers[character])
        elif nesting and character == nesting[-1]:
            array_lengths.discard(len(nesting))
            nesting.pop()
    return None


def _rust_locations(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8", errors="replace")
    code = _rust_code(text)
    line_starts = [0, *(match.end() for match in re.finditer("\n", text))]
    locations = []
    for match in _RUST_DECLARATION.finditer(code):
        start = match.start()
        line = bisect_right(line_starts, start)
        # Bound the signature window, including multiline declarations. This is
        # lexical navigation: macros, generated items and full bodies need reads.
        end = min(len(text), line_starts[line + 5] if line + 5 < len(line_starts) else len(text))
        boundary = _rust_declaration_end(code, match.end(), end)
        if boundary is not None:
            end = boundary
        window = text[start:end].strip()
        excerpt = window.encode()[:192].decode("utf-8", errors="ignore")
        locations.append(
            {
                "kind": match["kind"],
                "start_line": line,
                "end_line": line + excerpt.count("\n"),
                "text": excerpt,
                "window_complete": boundary is not None and excerpt == window,
            }
        )
    # Balance callable and type pointers when only a few fit. Keep source order
    # within each category; this is syntax selection, not contract assessment.
    categories = (frozenset({"fn"}), frozenset({"struct", "enum", "trait", "type"}), frozenset({"impl"}))
    groups = [[item for item in locations if item["kind"] in kinds] for kinds in categories]
    return [item for row in zip_longest(*groups) for item in row if item is not None]


def navigation_bytes(navigation: dict[str, Any]) -> int:
    """Count the complete compact navigation JSON, including its metadata."""
    return len(json.dumps(navigation, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())


def source_excerpt(path: str, content: bytes, budget: int) -> tuple[dict[str, Any], int]:
    """Share one file's allocation between navigation and its initial excerpt."""
    navigation: dict[str, Any] = {}
    if len(content) > budget and PurePosixPath(path).suffix == ".rs":
        locations = _rust_locations(content)
        candidate: dict[str, Any] = {"kind": "rust-lexical-declarations", "complete": False, "omitted_candidates": len(locations), "locations": []}
        for location in locations:
            trial = {**candidate, "omitted_candidates": candidate["omitted_candidates"] - 1, "locations": [*candidate["locations"], location]}
            if navigation_bytes(trial) <= budget * 3 // 4:
                candidate = trial
        if candidate["locations"]:
            navigation = candidate
    used = navigation_bytes(navigation) if navigation else 0
    excerpt = content[: budget - used].decode("utf-8", errors="ignore")
    return {"text": excerpt, "complete": excerpt.encode() == content, **({"navigation": navigation} if navigation else {})}, used + len(excerpt.encode())
