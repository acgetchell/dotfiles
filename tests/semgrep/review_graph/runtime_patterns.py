"""Semgrep fixtures for review-graph compiler boundary policies."""


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
