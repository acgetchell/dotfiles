"""Graph-specific identities over the shared package's exact-byte hashing API."""

import json

from research_repo_tools.evidence import sha256


def canonical_json(value: object, *, allow_nan: bool = True) -> str:
    """Preserve the graph's existing compact, ASCII-escaped JSON identities."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=allow_nan)


def digest_bytes(value: bytes) -> str:
    """Retain the graph's algorithm prefix over exact original bytes."""
    return "sha256:" + sha256(value)


def digest_json(value: object, *, allow_nan: bool = True) -> str:
    """Hash graph JSON without adopting a different serialization convention."""
    return digest_bytes(canonical_json(value, allow_nan=allow_nan).encode("utf-8"))
