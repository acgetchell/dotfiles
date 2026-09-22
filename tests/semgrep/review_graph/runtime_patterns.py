"""Semgrep fixtures for review-graph compiler boundary policies."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def compile_independent_review_unsafe(records: list[str]) -> str:
    """Show an unsafe one-argument lookup at a production boundary."""
    # ruleid: dotfiles.review-graph.no-bare-next
    return next(record for record in records if record == "selected")


def compile_independent_review_safe(records: list[str]) -> str:
    """Translate an absent lookup into a stable domain error."""
    # ok: dotfiles.review-graph.no-bare-next
    record = next((item for item in records if item == "selected"), None)
    if record is None:
        raise ValueError("selected record is missing")
    return record


def compile_independent_review() -> dict[str, str]:
    """Show an inline normalized-record builder in a compiler."""
    # ruleid: dotfiles.review-graph.compiler-uses-canonical-normalizer
    normalized = {"artifact_id": "artifact-1", "record_type": "review"}
    return normalized


def compile_review() -> dict[str, str]:
    """Use the canonical normalizer from a compiler."""
    # ok: dotfiles.review-graph.compiler-uses-canonical-normalizer
    normalized = _review_normalized_record()
    return normalized


def _review_normalized_record() -> dict[str, str]:
    """Keep normalized-record construction in its canonical helper."""
    # ok: dotfiles.review-graph.compiler-uses-canonical-normalizer
    return {"artifact_id": "artifact-1", "record_type": "review"}


def optional_attestation_unsafe(value: object) -> bool:
    """Show equality-based boolean membership at an untrusted boundary."""
    # ruleid: dotfiles.review-graph.boolean-membership-is-not-type-check
    return value in {None, True}


def negative_attestation_unsafe(value: object) -> bool:
    """Cover negated membership and False's equality with zero."""
    # ruleid: dotfiles.review-graph.boolean-membership-is-not-type-check
    return value not in {None, False}


def optional_attestation_safe(value: object) -> bool:
    """Use identity checks for an optional strict boolean."""
    # ok: dotfiles.review-graph.boolean-membership-is-not-type-check
    return value is None or value is True


def _write_bytes_once(path: Path, content: bytes) -> None:
    """Stand in for the direct create-once byte writer."""


def _write_text_once(path: Path, content: str) -> None:
    """Stand in for the direct create-once text writer."""


def _write_bytes_atomically_once(path: Path, content: bytes, *, mode: int) -> bool:
    """Stand in for the atomic create-once publisher."""
    return True


def recover_validation_launch(path: Path, content: bytes) -> None:
    """Pair interrupted-history risks with the approved publication primitive."""
    # ruleid: dotfiles.review-graph.recovery-publication-must-be-atomic
    _write_bytes_once(path, content)
    # ruleid: dotfiles.review-graph.recovery-publication-must-be-atomic
    _write_text_once(path, content.decode("utf-8"))
    # ok: dotfiles.review-graph.recovery-publication-must-be-atomic
    _write_bytes_atomically_once(path, content, mode=0o444)


def _publish_validation_continuation(path: Path, content: bytes) -> None:
    """Cover both wrapper writers and direct final-path writes."""
    # ruleid: dotfiles.review-graph.recovery-publication-must-be-atomic
    _write_bytes_once(path, content)
    # ruleid: dotfiles.review-graph.recovery-publication-must-be-atomic
    _write_text_once(path, content.decode("utf-8"))
    # ruleid: dotfiles.review-graph.recovery-publication-must-be-atomic
    path.write_bytes(content)
    # ruleid: dotfiles.review-graph.recovery-publication-must-be-atomic
    path.write_text(content.decode("utf-8"), encoding="utf-8")
    # ok: dotfiles.review-graph.recovery-publication-must-be-atomic
    _write_bytes_atomically_once(path, content, mode=0o600)


def unrelated_writer(path: Path, content: bytes) -> None:
    """Keep the rule scoped to recovery and continuation publication."""
    # ok: dotfiles.review-graph.recovery-publication-must-be-atomic
    _write_bytes_once(path, content)
