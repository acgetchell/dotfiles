"""Real Git staging, commit, and external-source handoffs for review-graph tests."""

import json
import shutil
import subprocess
from argparse import Namespace
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import review_graph_runtime as runtime
from capture_scope import _run_git, _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from review_graph_reuse import source_snapshot
from review_graph_runtime import JournalEventRequest, append_journal_event
from test_support_review_graph import ROUTING_CATALOG, SKILL_ROOT, _complete_structural_fixture_routing, _materialize, _run_test_git
from test_support_review_graph_evidence import (
    _accept,
    _compact_independent_payload,
    _execution_payload,
    _payload,
    _publish_worker_bytes,
    _save,
    _validation_payload,
)
from test_support_review_graph_lifecycle import _baseline_mutation_fixture


def _staging_fixture(
    tmp_path: Path, *, independent: bool = False, staging: str = "subset", mode: str = "baseline"
) -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Create a real staging transition and return its resume request and earlier audit."""
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    if staging == "mixed":
        (repository / "tool.py").write_text("value = 0\n")
        _run_test_git(git, "-C", str(repository), "add", "tool.py")
    (repository / "tool.py").write_text("value = 2\n")
    (repository / "state.rs").write_text("pub fn state() { let value = 2; }\n")
    if independent:
        template.update(concrete_change_target=True, change_target="git diff -- state.rs tool.py")
    capture = _scope_data(git, repository, mode, None, ())
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    journal = tmp_path / "old.jsonl"
    audit = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit")
    _publish_worker_bytes(audit, json.dumps(_payload(audit["dispatch"]["owned_paths"], dispatch=audit["dispatch"])).encode())
    append_journal_event(journal, lifecycle, JournalEventRequest(audit["node_id"], "in-flight"))
    _run_test_git(git, "-C", str(repository), "add", "." if staging == "all" else "tool.py")
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": _scope_data(git, repository, mode, None, ()),
        "dispatches_path": str(dispatches),
        "journal_path": str(journal),
        "artifact_store": str(tmp_path / "resumed"),
    }
    return git, repository, request, audit, entries


def _commit_audit_payload(dispatch: dict[str, Any], *, mode: str, change_target: str) -> dict[str, Any]:
    """Bind audit evidence to the Git comparison used by the selected capture mode."""
    payload = _payload(dispatch["owned_paths"], dispatch=dispatch)
    if mode == "branch":
        payload.update(
            commands_executed=[change_target],
            git_dependencies=[{"kind": "head", "command": change_target, "reason": "Compare inspected bytes against the immutable branch base."}],
        )
    return payload


def _commit_fixture(  # noqa: PLR0915 - complete real-Git execution and handoff fixture.
    tmp_path: Path, *, mode: str = "baseline", git_sensitive_review: bool = False
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    """Build a commit handoff from a real Git change and its earlier review evidence."""
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "justfile").write_text("ci:\n    test -f tool.py\n")
    (repository / "review-validation-contracts.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contracts": [
                    {
                        "contract_id": "fixture-ci",
                        "commands": ["just ci"],
                        "working_directories": ["."],
                        "implementation_paths": ["justfile"],
                        "input_scope": "repository",
                        "input_prefixes": [],
                        "git_inputs": [],
                        "deterministic": True,
                        "rationale": "The fixture recipe checks file existence only.",
                    }
                ],
            }
        )
    )
    _run_test_git(git, "-C", str(repository), "add", "justfile")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "CI recipe")
    (repository / "tool.py").write_text("value = 2\n")
    (repository / "state.rs").write_text("pub fn state() { let value = 2; }\n")
    template.update(concrete_change_target=True, change_target="git diff HEAD -- tool.py state.rs")
    local = template["validation_requirements"][0]
    local.update(commands=["just ci"], canonical_recipe="just ci")
    native = deepcopy(local)
    native.update(
        requirement_id="native-ci", commands=["native-ci-pending"], canonical_recipe=None, baseline=False, environment="native Linux", platform="linux"
    )
    template["validation_requirements"].append(native)
    template["pre_review_validation_requirement_ids"] = [local["requirement_id"]]
    base_ref = _run_git(git, repository, ("rev-parse", "HEAD^")).decode().strip() if mode == "branch" else None
    capture = _scope_data(git, repository, mode, base_ref, ())
    if mode == "branch":
        template["change_target"] = f"git diff {capture['merge_base']} -- tool.py state.rs"
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    lifecycle, dispatch_set, dispatches = _materialize(tmp_path, capture, plan)
    lifecycle["capture"] = capture
    entries = {entry["node_id"]: entry for entry in dispatch_set["dispatches"]}
    journal = tmp_path / "original.jsonl"
    local_entry = next(entry for entry in entries.values() if entry["dispatch"].get("validation_unit", {}).get("baseline"))
    native_entry = next(entry for entry in entries.values() if entry["dispatch"]["mode"] == "validation" and entry != local_entry)
    just = shutil.which("just")
    assert just is not None
    subprocess.run([just, "ci"], cwd=repository, check=True, capture_output=True)  # noqa: S603 - fixed fixture command.
    sources = {local_entry["node_id"]: _save(local_entry, lifecycle, journal, _validation_payload(local_entry))}
    for entry in entries.values():
        dispatch = entry["dispatch"]
        if dispatch["mode"] == "audit":
            payload = _commit_audit_payload(dispatch, mode=mode, change_target=template["change_target"])
            planned = next(unit for unit in dispatch["command_policy"]["planned_validation_units"] if "native-ci" in unit["requirement_ids"])
            payload["validation_requirements"] = [
                {
                    "requirement_id": "native-ci",
                    "planned_validation_digest": planned["planned_validation_digest"],
                    "owner": dispatch["skill_id"],
                    "reason": "Native target behavior requires CI",
                    "expected_evidence": "Native CI passes",
                }
            ]
            sources[entry["node_id"]] = _save(entry, lifecycle, journal, payload)
        elif dispatch["mode"] == "independent-review":
            payload = _compact_independent_payload(dispatch)
            if git_sensitive_review:
                payload["commands_executed"] = ["git log -1"]
                payload["git_dependencies"] = [{"kind": "history", "command": "git log -1", "reason": "Inspect the commit history."}]
            sources[entry["node_id"]] = _save(entry, lifecycle, journal, payload)
        elif dispatch["mode"] == "validation" and entry != local_entry:
            sources[entry["node_id"]] = _save(entry, lifecycle, journal, _validation_payload(entry, blocked=True))
    _run_test_git(git, "-C", str(repository), "switch", "-c", "fix/reviewed-commit")
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "Reviewed source")
    current = _scope_data(git, repository, mode, base_ref, ())
    lifecycle.pop("capture")
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": current,
        "journal_path": str(journal),
        "dispatches_path": str(dispatches),
        "artifact_store": str(tmp_path / "handoff"),
        "authorization": {
            "operation": "branch-commit",
            "repository_root": str(repository),
            "branch": current["branch"],
            "source_state": lifecycle["source_state"],
            "user_authorization": "Commit these reviewed changes on fix/reviewed-commit and push.",
        },
        "independent_reviews": {
            entry["node_id"]: {
                "change_target": entry["dispatch"]["change_target"],
                "comparison_commit": capture["merge_base"] if mode == "branch" else capture["head"],
                "reason": "Same captured worktree compared with the same immutable HEAD.",
            }
            for entry in entries.values()
            if entry["dispatch"]["mode"] == "independent-review"
        },
        "native_ci": {native_entry["node_id"]: {"commands": [f"native-ci --commit {current['head']}"], "checks": [{"name": "CI", "target": "linux"}]}},
    }
    if git_sensitive_review:
        request["independent_reviews"] = {}
    return request, entries, sources


def _handoff(  # noqa: PLR0913 - orthogonal fixture execution and contract controls.
    tmp_path: Path,
    *,
    dependencies: list[dict[str, str]] | None = None,
    result: str = "passed",
    failure_kind: str | None = None,
    prefixes: list[str] | None = None,
    contract: bool = True,
    instructions: bool = False,
    command: str | None = None,
    worktree: bool = False,
    readme: bool = False,
    repairs_completed: int = 0,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, Path, dict[str, Any]]:
    """Compile a validator in a real checkout and return its capture and evidence for reuse checks."""
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path, instructions=instructions)
    if readme:
        (repository / "README.md").write_text("# Fixture\n\n\nDescription.\n")
        template["consulted_routers"].append("docs-review-orchestrator")
    if command is not None:
        template["validation_requirements"][0].update(commands=[command], canonical_recipe=None)
    commands = template["validation_requirements"][0]["commands"]
    registry = {
        "schema_version": 1,
        "contracts": [
            {
                "contract_id": "fixture-check",
                "commands": commands,
                "working_directories": ["."],
                "implementation_paths": ["tool.py"],
                "input_scope": "repository" if prefixes is None else "prefixes",
                "input_prefixes": prefixes or [],
                "git_inputs": [],
                "deterministic": True,
                "rationale": "The fixture check depends on captured source only.",
            }
        ],
    }
    registry["contracts"].append({**registry["contracts"][0], "contract_id": "another-check", "commands": ["echo other"], "implementation_paths": ["LICENSE"]})
    if contract:
        (repository / "review-validation-contracts.json").write_text(json.dumps(registry))
    if worktree:
        (repository / "tool.py").write_text("value = 2\n")
    capture = _scope_data(git, repository, "worktree" if worktree else "baseline", None, ())
    if worktree:
        template["consulted_routers"].remove("rust-review-orchestrator")
        captured = set(source_snapshot(capture).captured_scope_paths)
        template["routing_overrides"] = [item for item in template["routing_overrides"] if captured.intersection(item["review_surface"])]
    _complete_structural_fixture_routing(template, list(source_snapshot(capture).captured_scope_paths))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    plan = replace(plan, review_lifecycle=replace(plan.review_lifecycle, repairs_completed=repairs_completed))
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    journal = tmp_path / "execution.jsonl"
    lifecycle.update(journal_path=str(journal), dispatches_path=str(dispatches))
    entry = next(item for item in entries["dispatches"] if item["result_contract"] == "compact-validation")
    payload = _execution_payload(entry, result, 1 if result == "failed" else 0, "1s")
    if failure_kind is not None:
        payload["failure_kind"] = failure_kind
    if dependencies is not None:
        payload["git_dependencies"] = dependencies
    _publish_worker_bytes(entry, json.dumps(payload).encode())
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    before.write_text(json.dumps(capture))
    after.write_text(json.dumps(capture))
    workspace = runtime.capture_workspace_snapshot(entry["dispatch"])
    workspace_path = tmp_path / "workspace.json"
    workspace_path.write_text(json.dumps(workspace))
    runtime._compile_node_from_files(
        lifecycle,
        Namespace(
            dispatches=dispatches,
            node_id=entry["node_id"],
            before_capture=before,
            after_capture=after,
            workspace_before=workspace_path,
            workspace_after=workspace_path,
            payload=None,
            status=None,
            limitation=None,
            journal=journal,
            output=tmp_path / "compiled.json",
        ),
    )
    metadata = json.loads(Path(entry["metadata_path"]).read_bytes())
    return lifecycle, entry, capture, git, repository, metadata


def _external(
    tmp_path: Path, *, changed: str = "README.md", repairs_completed: int = 0, dependency: str | None = None, git_dependency: str | None = None
) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
    """Create a handoff request that attributes an external source edit to the maintainer."""
    lifecycle, validator, capture, git, repository, _metadata = _handoff(
        tmp_path,
        dependencies=[{"kind": "index", "reason": "The fixture validation depends on staged contents."}] if git_dependency == "index" else [],
        prefixes=["tool.py"],
        readme=True,
        repairs_completed=repairs_completed,
    )
    entries = json.loads(Path(lifecycle["dispatches_path"]).read_bytes())
    for entry in entries["dispatches"]:
        if entry["dispatch"]["mode"] == "audit":
            payload = _payload(entry["dispatch"]["owned_paths"], dispatch=entry["dispatch"])
            if git_dependency is not None and "tool.py" in payload["files_inspected"]:
                command = "git --no-pager diff --cached -- tool.py"
                payload.update(commands_executed=[command], git_dependencies=[{"kind": git_dependency, "command": command, "reason": "Fixture Git input."}])
            if dependency is not None and "tool.py" in payload["files_inspected"]:
                payload["coverage_units"] = [
                    {
                        "unit_id": "tool",
                        "owned_paths": payload["files_inspected"],
                        "finding_indices": [],
                        "dependency_paths": [*payload["nearby_contract_owners"], *([] if dependency == "uncertain" else [dependency])],
                        "dependency_uncertainty": "Dynamic configuration is not fully classified." if dependency == "uncertain" else "",
                    }
                ]
            _accept(lifecycle, entry, payload)
    (repository / changed).write_text("# Fixture\n\nDescription.\n" if changed == "README.md" else "value = 42\n")
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": _scope_data(git, repository, "baseline", None, ()),
        "artifact_store": str(tmp_path / "external"),
        "external_source_actor": "maintainer",
        "external_source_attribution": "The maintainer confirmed this edit in the review chat.",
    }
    return request, validator, repository, entries
