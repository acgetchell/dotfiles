"""Language intersection protects future sidecars without flagging source globs."""

lazy from pathlib import Path

import pytest
import review_graph_globs as globs
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


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("/source/**", "/artifact-store/validation-001.*/**", False),
        ("/source", "/source-name/**", False),
        ("/source", "/source/**", True),
        ("/source/module.py", "/source/module.py/**", True),
        ("/source/module.py", "/source/module.p?", True),
        ("/source/module.py", "/source/*.rs", False),
        ("/source/[ab]/**", "/source/b/file", True),
        ("/source/[!ab]/**", "/source/b/file", False),
        ("/source/**/file", "/source/file", True),
        ("**/file", "/source/file", True),
        ("/source/*/file", "/source/file", False),
        ("/source/[]]", "/source/]", True),
        ("/source/[literal", "/source/[literal", True),
        ("/source//file", "/source/file", False),
        ("", "**", True),
        ("é/😀/**", "é/😀/file", True),
        ("é/😀/**", "é/😁/file", False),
    ],
)
def test_literal_prefix_filter_preserves_glob_language_boundaries(left: str, right: str, expected: bool) -> None:
    assert globs.path_globs_intersect(left, right) is expected
    assert globs.path_globs_intersect(right, left) is expected


def test_disjoint_source_and_artifact_directories_need_no_glob_state_search(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_search(*_args: object, **_kwargs: object) -> bool:
        pytest.fail("Disjoint literal directory prefixes must not enter the glob state search")

    monkeypatch.setattr(globs, "_intersects", unexpected_search)
    for source in range(265):
        for artifact in range(100):
            assert not globs.path_globs_intersect(
                f"/long/shared/session/repository/src/module_{source}.py/**", f"/long/shared/session/proof/audit-{artifact:03}.*/*"
            )
