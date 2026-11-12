"""Reject ambiguous transition variants at the retained-document boundary."""

from dataclasses import asdict, replace
from typing import Any

import pytest
from review_graph_reuse import SNAPSHOT_FORMAT, ReviewSourceSnapshot, metadata_transition, regular_file_fingerprint


def _metadata_change() -> dict[str, Any]:
    before = ReviewSourceSnapshot(SNAPSHOT_FORMAT, "/fixture", "baseline", "head", "main", None, None, (), (), "a" * 64, "b" * 64, "", "c" * 64, (), ())
    before = replace(before, repository_state_fingerprint=before.computed_fingerprint())
    after = replace(before, index_fingerprint="d" * 64)
    after = replace(after, repository_state_fingerprint=after.computed_fingerprint())
    return {"before": asdict(before), "after": asdict(after)}


@pytest.mark.parametrize(
    "extra", [{"repair_paths": []}, {"repair_attribution": "Agent edited content"}, {"staging_attribution": "Staged a repair"}, {"unknown": True}]
)
def test_metadata_parser_does_not_discard_unowned_evidence(extra: dict[str, Any]) -> None:
    raw = _metadata_change()
    assert metadata_transition(raw).before.index_fingerprint == "c" * 64
    with pytest.raises(ValueError, match="transition"):
        metadata_transition({**raw, **extra})


def test_regular_identity_rejects_nul_path() -> None:
    with pytest.raises(ValueError, match="repository path"):
        regular_file_fingerprint("source\0.py", b"source")
