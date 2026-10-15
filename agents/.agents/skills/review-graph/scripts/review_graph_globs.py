"""Intersect path glob languages without treating either pattern as literal text."""

from fnmatch import fnmatchcase
from functools import lru_cache


@lru_cache(maxsize=4096)
def _tokens(pattern: str) -> tuple[str, ...]:
    tokens = []
    index = 0
    while index < len(pattern):
        end = index + 1
        if pattern[index] == "[":
            closing = end + (pattern[end : end + 1] == "!")
            closing += pattern[closing : closing + 1] == "]"
            closing = pattern.find("]", closing)
            if closing >= 0:
                end = closing + 1
        tokens.append(pattern[index:end])
        index = end
    return tuple(tokens)


@lru_cache(maxsize=4096)
def _characters_overlap(left: str, right: str) -> bool:
    if len(left) == 1 and left not in "*?[":
        return left not in {"/", "\0"} and fnmatchcase(left, right)
    if len(right) == 1 and right not in "*?[":
        return right not in {"/", "\0"} and fnmatchcase(right, left)
    # Character classes only change membership at literal/range boundaries.
    # Include their neighbours and the Unicode endpoints for negated classes.
    boundaries = {0, 1, 0x10FFFF}
    for character in left + right:
        boundaries.update(value for value in (ord(character) - 1, ord(character), ord(character) + 1) if 0 <= value <= 0x10FFFF)
    return any(chr(value) not in {"/", "\0"} and all(pattern == "*" or fnmatchcase(chr(value), pattern) for pattern in (left, right)) for value in boundaries)


@lru_cache(maxsize=4096)
def _intersects(left: tuple[str, ...], right: tuple[str, ...], *, paths: bool) -> bool:
    if left == right:
        return True
    pending = [(0, 0)]
    visited = set()
    star = "**" if paths else "*"
    while pending:
        i, j = pending.pop()
        if (i, j) in visited:
            continue
        visited.add((i, j))
        if i == len(left) and j == len(right):
            return True
        if i < len(left) and left[i] == star:
            pending.append((i + 1, j))
        if j < len(right) and right[j] == star:
            pending.append((i, j + 1))
        if i == len(left) or j == len(right):
            continue
        a, b = left[i], right[j]
        overlap = (star in (a, b) or _intersects(_tokens(a), _tokens(b), paths=False)) if paths else _characters_overlap(a, b)
        if overlap:
            pending.append((i if a == star else i + 1, j if b == star else j + 1))
    return False


def path_globs_intersect(left: str, right: str) -> bool:
    """Respect directory boundaries; ** alone spans zero or more components."""
    return _intersects(tuple(left.split("/")), tuple(right.split("/")), paths=True)
