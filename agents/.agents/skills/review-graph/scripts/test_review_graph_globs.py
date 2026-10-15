"""Language intersection protects future sidecars without flagging source globs."""

lazy from pathlib import Path

import pytest
from review_graph_isolation import isolation_violations


@pytest.mark.parametrize(
    ("operand", "blocked"),
    [
        ("/artifact-store/*.receipt.jsonl", True),
        ("/artifact-store/validation-001.timing-0.receipt.jsonl", True),
        ("/artifact-store/validation-*.*/nested/*.jsonl", True),
        ("/artifact-store/**/receipt.jsonl", True),
        ("/artifact-store/validation-00[1-3].*.jsonl", True),
        ("/artifact-store/validation-00[2-3].*.jsonl", False),
        ("/source/*.receipt.jsonl", False),
        ("/source/**/validation-001.*", False),
        ("/artifact-store/other/*.receipt.jsonl", False),
    ],
)
def test_intersecting_sidecars_keep_directory_identity(tmp_path: Path, operand: str, blocked: bool) -> None:
    dispatch = {
        "fresh_context": True,
        "mode": "audit",
        "repository_root": str(tmp_path),
        "fresh_context_forbidden_artifacts": ["/artifact-store/validation-001.*"],
    }
    assert bool(isolation_violations(dispatch, {"commands_executed": [f"cat {operand}"]})) is blocked


def test_hash_in_filename_cannot_hide_later_peer_glob(tmp_path: Path) -> None:
    dispatch = {
        "fresh_context": True,
        "mode": "audit",
        "repository_root": str(tmp_path),
        "fresh_context_forbidden_artifacts": ["/artifact-store/validation-001.*"],
    }
    assert isolation_violations(dispatch, {"commands_executed": ["cat tool.py#suffix; cat /artifact-store/*.receipt.jsonl"]})
