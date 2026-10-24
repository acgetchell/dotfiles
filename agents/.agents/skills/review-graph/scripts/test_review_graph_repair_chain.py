"""Saved ordinary repair captures compose with later interleaved staging."""

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_git import intervening_metadata_blockers
from review_graph_reuse import ObservedSourceTransition, metadata_states, metadata_transition, source_snapshot
from test_review_graph_interleaved import _interleaved
from test_review_graph_repair_staging import _finish_repair
from test_review_graph_runtime import _baseline_mutation_fixture, _run_test_git


def _repair_chain(tmp_path: Path, dependency: str) -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[str, Any], dict[Path, bytes]]:
    git, repository, request, audit, history = _interleaved(tmp_path, dependency)
    request.pop("interleaved_staging")
    _run_test_git(git, "-C", str(repository), "reset", "HEAD", "--", "state.rs")
    request["new_capture"] = _scope_data(git, repository, "baseline", None, ())
    first = runtime.advance_after_mutation(request)
    path = repository / "state.rs"
    path.write_text("pub fn state() { assert_eq!(4, 4); }\n")
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    path.write_text("pub fn state() { assert_eq!(5, 5); }\n")
    current = _scope_data(git, repository, "baseline", None, ())
    history[repository / ".git" / "index"] = (repository / ".git" / "index").read_bytes()
    history.update({path: path.read_bytes() for path in Path(first["lifecycle_input_path"]).parent.rglob("*") if path.is_file()})
    second_request = {
        **request,
        **first["lifecycle_input"],
        "repair_epoch": 2,
        "authorization_before": "review-and-fix",
        "previous_capture": first["capture"],
        "new_capture": current,
        "sources": [{key: audit[key] for key in ("artifact_path", "metadata_path")}],
        "interleaved_staging": {
            "repair_attribution": "The agent performed the second authorized state.rs repair.",
            "staging_attribution": "The maintainer staged state.rs during the second repair.",
        },
    }
    return git, repository, first, second_request, audit, history


@pytest.mark.parametrize("dependency", ["source", "source-discovery", "index"])
def test_ordinary_then_interleaved_repair_preserves_only_eligible_audits(tmp_path: Path, dependency: str) -> None:
    git, repository, first, request, audit, history = _repair_chain(tmp_path, dependency)
    original = deepcopy(request)
    evidence_id = audit["dispatch"]["evidence_id"]
    assert evidence_id in first["reused_evidence_ids"]
    result = runtime.advance_after_mutation(request)
    assert (evidence_id in result["reused_evidence_ids"]) is (dependency != "index")
    if dependency != "index":
        transition = result["new_plan"]["audit_reuse_transitions"][0]
        chain = tuple(metadata_transition(item) for item in json.loads(json.dumps(transition["metadata_transitions"])))
        assert len(chain) == 2
        assert isinstance(chain[0], ObservedSourceTransition)
        assert chain[0].before.source_state == tuple(first["old_source_state"])
        assert chain[0].after == source_snapshot(first["capture"])
        assert chain[1].before == chain[0].after
        assert chain[1].after == source_snapshot(request["new_capture"])
        assert metadata_states(chain[0].before.source_state, chain)[-1] == tuple(result["new_source_state"])
        assert "repair_attribution" not in asdict(chain[0])
    else:
        decision = next(item for item in result["reuse_decisions"] if item["node_id"] == audit["node_id"])
        assert decision["reason_code"] == "metadata-dependencies-changed"
    _finish_repair(tmp_path, result)
    assert {path: path.read_bytes() for path in history} == history
    assert _scope_data(git, repository, "baseline", None, ()) == request["new_capture"]
    assert request == original


@pytest.fixture(scope="module")
def ordinary_captures(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], dict[str, Any]]:
    git, repository, _template, before, _plan = _baseline_mutation_fixture(tmp_path_factory.mktemp("ordinary-repair-captures"))
    (repository / "state.rs").write_text("pub fn state() { assert_eq!(1, 1); }\n")
    return before, _scope_data(git, repository, "baseline", None, ())


@pytest.mark.parametrize("field", ["index_fingerprint", "head", "branch", "base_ref", "capture_mode", "captured_scope_paths", "repository_selection_paths"])
def test_source_bridge_rejects_a_changed_boundary(ordinary_captures: tuple[dict[str, Any], dict[str, Any]], field: str) -> None:
    before, after = ordinary_captures
    changed = deepcopy(after)
    if field == "index_fingerprint":
        changed[field] = "0" * 64
    elif field in {"captured_scope_paths", "repository_selection_paths"}:
        changed[field] = ["state.rs"]
    elif field == "capture_mode":
        changed[field] = "staged"
    else:
        changed[field] = "other"
    changed["repository_state_fingerprint"] = source_snapshot(changed).computed_fingerprint()
    with pytest.raises(ValueError, match="observed source bridge"):
        metadata_transition({"before": before, "after": changed, "observed_source_only": True})


@pytest.mark.parametrize(
    "extra",
    [
        {"observed_source_only": False},
        {"repair_epoch": 1},
        {"external_source_actor": "maintainer"},
        {"git_context_authorization": "approved"},
        {"commit_handoff": {}},
    ],
)
def test_source_bridge_rejects_mixed_or_invalid_attribution(ordinary_captures: tuple[dict[str, Any], dict[str, Any]], extra: dict[str, Any]) -> None:
    before, after = ordinary_captures
    with pytest.raises(ValueError, match="cannot invent or combine transition attribution"):
        metadata_transition({"before": before, "after": after, "observed_source_only": True, **extra})


def test_repeated_source_identity_keeps_observed_git_history(tmp_path: Path) -> None:
    git, repository, _template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    path = repository / "state.rs"
    original = path.read_bytes()
    path.write_text("pub fn state() { assert!(true); }\n")
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    path.write_bytes(original)
    staged = _scope_data(git, repository, "baseline", None, ())
    _run_test_git(git, "-C", str(repository), "reset", "HEAD", "--", "state.rs")
    restored = _scope_data(git, repository, "baseline", None, ())
    assert restored == capture
    path.write_text("pub fn state() { assert_eq!(4, 4); }\n")
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    path.write_text("pub fn state() { assert_eq!(5, 5); }\n")
    current = _scope_data(git, repository, "baseline", None, ())
    state = source_snapshot(capture).source_state
    history = [{"before": capture, "after": staged}, {"before": staged, "after": restored}]
    latest = {
        "before": restored,
        "after": current,
        "repair_epoch": 1,
        "repair_paths": ["state.rs"],
        "repair_attribution": "The agent performed the authorized repair.",
        "staging_attribution": "The maintainer staged during the repair.",
    }
    chain = runtime._metadata_chain_from(
        {
            "plan": {"audit_reuse_transitions": [{"source_state": list(state), "target_state": list(state), "metadata_transitions": history}]},
            "external_metadata_transitions": [latest],
        },
        state,
    )
    assert len(chain) == 3
    assert metadata_states(state, chain) == (state, source_snapshot(staged).source_state, state, source_snapshot(current).source_state)
    for dependency in ("index", "history"):
        blockers = intervening_metadata_blockers({"git_dependencies": [{"kind": dependency, "reason": "The judgment depends on observed Git state."}]}, chain)
        assert any(item.get("dependency") == dependency for item in blockers)
