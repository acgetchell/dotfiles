"""Shared structural builders; the test_ prefix excludes them from frozen runtimes."""

import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from capture_scope import _scope_data
from research_repo_tools.process import run_command_bytes
from review_graph_plan import GraphPlan, plan_from_document
from review_graph_runtime import build_routing_projection_document, main, materialize_dispatches, publish_worker_payload_bytes
from review_graph_timing import timing_documents

SKILL_ROOT = Path(__file__).resolve().parents[2]
ROUTING_CATALOG = Path(__file__).resolve().parents[1] / "references" / "routing-catalog.json"
VALIDATOR_SKILL = SKILL_ROOT / "review-validator" / "SKILL.md"
VALIDATOR_CONTRACT = SKILL_ROOT / "review-validator" / "references" / "graph-dispatch.md"
STATE_FIXTURE = "agents/.agents/skills/review-graph/scripts/fixtures/state.rs"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "references" / "schemas"


def _publish(entry: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Publish fixture evidence through the contract written for this worker."""
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    return publish_worker_payload_bytes(contract, json.dumps(payload).encode())


def _prepare_fixture_timing(entry: dict[str, Any]) -> None:
    """Explicitly approve a fixture shell without executing the dispatched command."""
    writes, _manifest = timing_documents(entry["dispatch"], {"shell_argv": ["/bin/sh", "-c"]})
    for path, content in writes.items():
        path.write_bytes(content)


def _prepare_all_fixture_timing(dispatch_set: dict[str, Any]) -> None:
    """Prepare missing validator transport for lifecycle-only execution fixtures."""
    for entry in dispatch_set["dispatches"]:
        dispatch = entry["dispatch"]
        if dispatch["mode"] == "validation" and not Path(dispatch["timing_prerequisite"]["manifest_path"]).exists():
            _prepare_fixture_timing(entry)


def _finalize_fixture_proof(result: dict[str, Any], *, output: Path) -> dict[str, Any]:
    """Finalize a continuation through the CLI and read its saved proof."""
    assert (
        main(
            [
                "finalize-proof",
                "--input",
                result["lifecycle_input_path"],
                "--dispatches",
                result["dispatches_path"],
                "--journal",
                result["journal_path"],
                "--current-capture",
                result["capture_path"],
                "--output",
                str(output),
            ]
        )
        == 0
    )
    return json.loads(output.read_bytes())


def _captured_rust_repository(tmp_path: Path, *, branch: bool = False) -> dict[str, Any]:
    """Capture fresh Git state with the real source, ignore rules and instructions."""
    git = shutil.which("git")
    assert git is not None
    repository = tmp_path / "repository"
    repository.mkdir()
    source_root = SKILL_ROOT.parents[2]
    for name in (".gitignore", "AGENTS.md"):
        (repository / name).write_bytes((source_root / name).read_bytes())
    source = repository / STATE_FIXTURE
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pub fn previous_state() {}\n" if branch else (source_root / STATE_FIXTURE).read_bytes())
    for arguments in (
        ("init", "--initial-branch=main"),
        ("config", "user.email", "review@example.com"),
        ("config", "user.name", "Review Test"),
        ("add", "."),
        ("commit", "-m", "Initial fixture"),
    ):
        run_command_bytes(git, ("-C", str(repository), *arguments))
    base = None
    if branch:
        base = run_command_bytes(git, ("-C", str(repository), "rev-parse", "HEAD")).stdout.decode().strip()
        source.write_bytes((source_root / STATE_FIXTURE).read_bytes())
        run_command_bytes(git, ("-C", str(repository), "add", STATE_FIXTURE))
        run_command_bytes(git, ("-C", str(repository), "commit", "-m", "Update fixture state"))
    return _scope_data(git, repository, "branch" if branch else "baseline", base, (STATE_FIXTURE,))


def _sparse_plan_document() -> dict[str, Any]:
    """Build a compact Rust routing fixture with a no-op baseline for graph tests.

    The two selected audits share a source file so tests can exercise distinct
    evidence owners. Tests that need verified source state supply a real capture.
    """
    return {
        "captured_paths": [STATE_FIXTURE],
        "concrete_change_target": False,
        "consulted_routers": ["review-graph", "rust-review-orchestrator"],
        "execution_profile": "grouped",
        "release_readiness": False,
        "routing_overrides": [
            {
                "applicability_evidence": ["state.rs changes Rust state behavior"],
                "catalog_id": "rust.invariants",
                "disposition": "selected",
                "owners": ["rust"],
                "reason": "state transition behavior changed",
                "review_surface": [STATE_FIXTURE],
            },
            {
                "catalog_id": "rust.build",
                "disposition": "selected",
                "reason": "Fixture explicitly exercises the Rust build owner and its independent evidence",
                "applicability_evidence": ["The synthetic source participates in a build contract"],
                "owners": ["rust"],
                "review_surface": [STATE_FIXTURE],
            },
            {
                "catalog_id": "rust.style",
                "disposition": "not-applicable",
                "reason": "This synthetic two-audit protocol fixture exercises state and build evidence",
                "applicability_evidence": ["The fixture has a single state function and specifies no file convention"],
                "owners": ["rust"],
                "review_surface": [STATE_FIXTURE],
            },
        ],
        "scope_mode": "baseline",
        "validation_requirements": [
            {
                "allowed_artifacts": [],
                "artifact_owner": "repository",
                "authority": "repository baseline",
                "baseline": True,
                "canonical_recipe": "true",
                "capture_command": "capture_scope.py --mode baseline",
                "captured_paths": [STATE_FIXTURE],
                "commands": ["true"],
                "dependency_policy": "stop-on-failure",
                "elapsed_time_budget": "30s",
                "environment": "current host",
                "evidence_id": None,
                "execution_strategy": "sequential",
                "expected_evidence": "baseline command completes",
                "features": [],
                "independence_basis": "none",
                "meaningful_skips": [],
                "mutation_classification": "non-mutating under validation-only",
                "mutation_lock": "repository read-only",
                "planning_blocker": None,
                "platform": "current host",
                "request": "validate compact routing fixture",
                "requested_scope": "baseline",
                "required": True,
                "requirement_id": "baseline-validation",
                "selection_reason": "bounded graphs require baseline validation",
                "source_state": ["scope", "worktree", "repository"],
                "toolchain": "system",
                "working_directories": [str(SKILL_ROOT.parents[2])],
            }
        ],
    }


def _assessed_fixture_candidates(paths: list[str], routers: list[str], selected: dict[str, str]) -> list[dict[str, Any]]:
    """Supply explicit judgments for structural fixtures; never production routing."""
    projection = build_routing_projection_document(
        {"captured_paths": paths, "consulted_routers": routers}, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,)
    )
    return [
        {
            "catalog_id": entry["catalog_id"],
            "disposition": "selected" if entry["catalog_id"] in selected else "not-applicable",
            "reason": selected.get(entry["catalog_id"], "Fixture contract has no change to this specialist's concern"),
            "applicability_evidence": [selected.get(entry["catalog_id"], "Explicit fixture scope excludes this concern; path match is only a candidate")],
            "review_surface": entry["matched_paths"],
            "owners": ["documentation" if entry["catalog_id"].startswith("docs.") else entry["catalog_id"].split(".")[0]],
        }
        for entry in projection["entries"]
        if entry["target_kind"] == "leaf" and entry["matched_paths"] and not entry["catalog_id"].startswith("repo.")
    ]


def _run_test_git(git: str, *arguments: str) -> None:
    """Run a fixture Git command and raise on a failed setup step."""
    subprocess.run([git, *arguments], check=True, capture_output=True)  # noqa: S603 - resolved Git test fixture.


def _baseline_capture() -> dict[str, Any]:
    """Build a baseline capture with fixed path bounds and source fingerprints."""
    return {
        "base_ref": None,
        "branch": "main",
        "capture_mode": "baseline",
        "captured_path_line_bounds": {STATE_FIXTURE: 3},
        "captured_scope_paths": [STATE_FIXTURE],
        "captured_worktree_fingerprint": "captured-worktree",
        "head": "head",
        "merge_base": None,
        "repository_root": str(SKILL_ROOT.parents[2]),
        "repository_state_fingerprint": "captured-repository",
        "requested_paths": [],
        "scope_fingerprint": "captured-scope",
        "status": [],
        "untracked_paths": [],
    }


def _json_plan(plan: GraphPlan) -> dict[str, object]:
    """Round-trip a plan through JSON so callers see the same field types as a saved plan."""
    value = json.loads(json.dumps(asdict(plan)))
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _sparse_plan() -> GraphPlan:
    """Parse the minimal planning document against the repository's real routing catalog."""
    return plan_from_document(_sparse_plan_document(), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=SKILL_ROOT.parents[2])


def _set_fixture_routing(document: dict[str, Any], decision: dict[str, Any]) -> None:
    """Replace a fixture judgment when a test changes that owner's contract."""
    document["routing_overrides"] = [item for item in document["routing_overrides"] if item["catalog_id"] != decision["catalog_id"]]
    document["routing_overrides"].append(decision)


def _complete_structural_fixture_routing(document: dict[str, Any], paths: list[str]) -> None:
    """Make this broad protocol fixture's intentional all-owner selection explicit."""
    projection = build_routing_projection_document(
        {"captured_paths": paths, "consulted_routers": document["consulted_routers"]}, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,)
    )
    existing = {item["catalog_id"] for item in document["routing_overrides"]}
    document["routing_overrides"].extend(
        {
            "catalog_id": entry["catalog_id"],
            "disposition": "selected",
            "reason": "Protocol fixture deliberately exercises every candidate owner",
            "applicability_evidence": ["Synthetic multi-owner lifecycle and identity coverage"],
            "review_surface": entry["matched_paths"],
            "owners": ["documentation" if entry["catalog_id"].startswith("docs.") else entry["catalog_id"].split(".")[0]],
        }
        for entry in projection["entries"]
        if entry["target_kind"] == "leaf" and entry["matched_paths"] and entry["catalog_id"] not in existing and not entry["catalog_id"].startswith("repo.")
    )


def _late_handoff_replan() -> GraphPlan:
    """Build the Rust plan that results from a handoff discovered after initial routing."""
    document = _sparse_plan_document()
    document["consulted_routers"] = ["review-graph", "rust-review-orchestrator", "python-review-orchestrator"]
    document["routing_overrides"] = [
        next(item for item in document["routing_overrides"] if item["catalog_id"] == "rust.style"),
        {
            "applicability_evidence": ["accepted build audit from the unchanged source state"],
            "catalog_id": "rust.build",
            "disposition": "exact-evidence-reused",
            "evidence_id": "review:audit-001",
            "owners": ["rust"],
            "reason": "the prior Rust build audit is exact for this source state",
            "review_surface": [STATE_FIXTURE],
        },
        {
            "applicability_evidence": ["accepted audit from the unchanged source state"],
            "catalog_id": "rust.invariants",
            "disposition": "exact-evidence-reused",
            "evidence_id": "review:audit-002",
            "owners": ["rust"],
            "reason": "the prior Rust invariant audit is exact for this source state",
            "review_surface": [STATE_FIXTURE],
        },
        {
            "applicability_evidence": ["accepted handoff identified notebook ownership"],
            "catalog_id": "repo.python",
            "disposition": "selected",
            "reason": "late handoff requires the Python surface router",
        },
        {
            "applicability_evidence": ["accepted handoff identified notebook semantics"],
            "catalog_id": "python.notebook",
            "disposition": "selected",
            "owners": ["python"],
            "reason": "late handoff requires a notebook audit",
            "review_surface": [STATE_FIXTURE],
        },
    ]
    return plan_from_document(document, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=SKILL_ROOT.parents[2])


def _worker_input_fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Materialize the sparse plan's worker inputs in a temporary artifact store."""
    document = {
        "artifact_store": str(tmp_path / "proof"),
        "authorization": "review-only",
        "plan": _json_plan(_sparse_plan()),
        "repository_root": str(SKILL_ROOT.parents[2]),
        "source_state": ["scope", "worktree", "repository"],
        "state_verification_command": "capture_scope.py --mode baseline",
    }
    return document, materialize_dispatches(document)


def _materialize(tmp_path: Path, capture: dict[str, Any], plan: Any) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Persist dispatches bound to the scope, worktree, and repository fingerprints in the capture."""
    state = [capture[key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")]
    lifecycle = {"plan": _json_plan(plan), "source_state": state}
    entries = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "old"),
            "repository_root": capture["repository_root"],
            "authorization": "review-only",
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    dispatches = tmp_path / "dispatches.json"
    dispatches.write_text(json.dumps(entries))
    return lifecycle, entries, dispatches
