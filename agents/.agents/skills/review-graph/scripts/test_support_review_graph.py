"""Shared structural builders; the test_ prefix excludes them from frozen runtimes."""

import shutil
from pathlib import Path
from typing import Any

from capture_scope import _scope_data
from research_repo_tools.process import run_command_bytes
from review_graph_runtime import build_routing_projection_document
from review_graph_timing import timing_documents

SKILL_ROOT = Path(__file__).resolve().parents[2]
ROUTING_CATALOG = Path(__file__).resolve().parents[1] / "references" / "routing-catalog.json"
VALIDATOR_SKILL = SKILL_ROOT / "review-validator" / "SKILL.md"
VALIDATOR_CONTRACT = SKILL_ROOT / "review-validator" / "references" / "graph-dispatch.md"
STATE_FIXTURE = "agents/.agents/skills/review-graph/scripts/fixtures/state.rs"


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
