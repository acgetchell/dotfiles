"""Starter bundles and frozen CLI sessions for review-graph tests."""

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import review_graph_runtime as runtime
from capture_scope import _scope_data, persist_capture
from review_graph_bootstrap import main
from review_graph_reuse import source_snapshot
from review_graph_session import freeze_runtime
from review_graph_starter import STARTER_EXAMPLE
from test_support_review_graph import SKILL_ROOT, _assessed_fixture_candidates, _captured_rust_repository, _complete_structural_fixture_routing, _run_test_git
from test_support_review_graph_lifecycle import _baseline_mutation_fixture
lazy import pytest


def _fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use fresh branch history with repository-owned ignore rules and source."""
    capture = _captured_rust_repository(tmp_path, branch=True)
    choices = json.loads(STARTER_EXAMPLE.read_text())
    root = tmp_path / "proof ' space $(no-shell-expansion)"
    root.mkdir()
    choices.update(
        artifact_root=str(root),
        consulted_routers=["review-graph", "rust-review-orchestrator"],
        ignored_outputs=[{"path": ".pytest_cache", "kind": "cache"}],
        command_policy={"disposition": "allowed", "reason": "Deterministic stand-in emits text and exits; no Git or source mutation."},
    )
    choices["routing_overrides"] = _assessed_fixture_candidates(
        capture["captured_scope_paths"],
        choices["consulted_routers"],
        {"rust.invariants": "Scripted fixture exercises invariant-owner dispatch", "rust.build": "Scripted fixture exercises build-owner dispatch"},
    )
    host = tmp_path / "host"
    host.mkdir()
    just = host / "just"
    just.write_text('#!/bin/sh\nprintf "%s\\n" "$UV_CACHE_DIR"\nexit 7\n')
    just.chmod(0o755)
    choices["execution_prerequisites"] = {
        "executables": [str(just)],
        "native_available": True,
        "reason": "POSIX stand-in inspected for this deterministic fixture; no recipe is run by bootstrap.",
    }
    return capture, choices


def _invoke(tmp_path: Path, capture: dict[str, Any], choices: dict[str, Any]) -> tuple[int, Path]:
    """Write the capture and starter choices, then return the CLI status and output path."""
    capture_path, choices_path, output = (tmp_path / name for name in ("capture.json", "choices.json", "bootstrap.json"))
    capture_path.write_text(json.dumps(capture, indent=2) + "\n")
    choices_path.write_text(json.dumps(choices, indent=2) + "\n")
    return main(["--capture", str(capture_path), "--starter-config", str(choices_path), "--output", str(output)]), output


def _cli(script: Path, *arguments: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run the session script without writing bytecode and return its captured byte streams."""
    return subprocess.run(  # noqa: S603 - fixed repository scripts with isolated fixture paths.
        [sys.executable, "-B", str(script), *arguments], input=stdin, capture_output=True, check=True, timeout=60
    )


def _use_historical_views(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Materialize the legacy unbound format using different frozen guidance."""
    live = tmp_path / "historical-skills"
    shutil.copytree(SKILL_ROOT, live, ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "*.pyc"))
    renderer = live / "review-graph/scripts/review_graph_views.py"
    content = renderer.read_text().replace("Read skill/instructions", "Historical guidance: read skill/instructions")
    renderer.write_text(content.replace(' + "\\n").encode()', ' + "\\r\\n").encode()'))
    reference = freeze_runtime(live, tmp_path / "frozen", repository=SKILL_ROOT.parents[2])
    monkeypatch.setattr(runtime, "verify_current_snapshot", lambda: reference)
    # Historical materialization did not bind guidance into the canonical input.
    monkeypatch.setattr(runtime, "bind_execution_instructions", lambda _entry: None)
    return reference


def _frozen_run(
    tmp_path: Path, *, early: bool, input_selection: bool = False, log_kind: str = "file", large_scope: bool = False
) -> tuple[str, Path, dict[str, Any], dict[str, Any], Path, Path]:
    """Prepare a Git repository and materialize its workers with a frozen copy of the runtime."""
    git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    if large_scope:
        for index in range(200):
            (repository / f"long_baseline_document_name_{index:04d}.txt").write_text("unchanged baseline evidence\n")
        template["captured_path_dispositions"].append(
            {
                "paths": [f"long_baseline_document_name_{index:04d}.txt" for index in range(200)],
                "disposition": "historical",
                "reason": "Inactive text records retained to exercise large inventory transport",
                "catalog_ids": [],
            }
        )
        _run_test_git(git, "-C", str(repository), "add", ".")
        _run_test_git(git, "-C", str(repository), "commit", "-m", "large baseline")
        capture = _scope_data(git, repository, "baseline", None, ())
        _complete_structural_fixture_routing(template, list(source_snapshot(capture).captured_scope_paths))
    requirement = template["validation_requirements"][0]
    isolation = tmp_path / "validator"
    isolation.mkdir()
    if log_kind == "aliased-directory":
        alias = tmp_path / "validator-alias"
        alias.symlink_to(isolation, target_is_directory=True)
        isolation = alias
    log = artifact = isolation / "ci.log"
    if log_kind in {"directory", "aliased-directory"}:
        artifact = isolation / "logs"
        log = artifact / "nested" / "ci.log"
        log.parent.mkdir(parents=True)
        (artifact / "empty").mkdir()
        outside = tmp_path / "outside.log"
        outside.write_text("external bytes must not be archived\n")
        (artifact / "external-link").symlink_to(outside)
    elif log_kind == "symlink":
        artifact = isolation / "log-link"
        artifact.symlink_to(log.name)
    requirement.update(
        commands=["printf passed > " + shlex.quote(str(log))],
        canonical_recipe=None,
        requires_isolation=True,
        isolation_root=str(isolation),
        working_directories=[str(isolation)],
        allowed_artifacts=[{"path": str(artifact), "kind": "log", "repository_status": "outside-repository"}],
    )
    if input_selection:
        (repository / "enumerate.sh").write_text('git -C "$1" ls-files --cached --others --exclude-standard -z\n')
        template["routing_overrides"].append(
            {
                "catalog_id": "repo.tooling",
                "disposition": "selected",
                "reason": "The fixture's validator invokes this repository input-selection script",
                "applicability_evidence": ["enumerate.sh selects the gate's inputs"],
                "review_surface": ["enumerate.sh"],
                "owners": ["tooling"],
            }
        )
        requirement.update(commands=[shlex.join(["sh", str(repository / "enumerate.sh"), str(repository)]) + " > " + shlex.quote(str(log))])
        capture = _scope_data(git, repository, "baseline", None, ())
        _complete_structural_fixture_routing(template, list(source_snapshot(capture).captured_scope_paths))
    snapshot = source_snapshot(capture)
    template.update(
        authorization="review-and-fix",
        concrete_change_target=True,
        change_target=shlex.join(["git", "diff", snapshot.head, "--", *(["."] if large_scope else snapshot.captured_scope_paths)]),
    )
    if early:
        template["pre_review_validation_requirement_ids"] = [requirement["requirement_id"]]
    capture_path, template_path, bundle_path = (tmp_path / name for name in ("initial-capture.json", "template.json", "bootstrap.json"))
    capture_path.write_text(json.dumps(capture))
    template_path.write_text(json.dumps(template))
    _cli(
        SKILL_ROOT / "review-graph/scripts/review_graph_bootstrap.py",
        "--capture",
        str(capture_path),
        "--input",
        str(template_path),
        "--output",
        str(bundle_path),
    )
    bundle = json.loads(bundle_path.read_bytes())
    assert bundle["validation_reuse_prerequisite"]["registry_present"] is False
    frozen_runtime = Path(bundle["runtime_snapshot"]["path"]).parent / "skills/review-graph/scripts/review_graph_runtime.py"
    dispatch_path = tmp_path / "dispatches.json"
    _cli(frozen_runtime, "materialize-dispatches", "--input", str(bundle_path), "--output", str(dispatch_path))
    return git, repository, bundle, json.loads(dispatch_path.read_bytes()), frozen_runtime, dispatch_path


def _compile(  # noqa: PLR0913, PLR0917 - mirror the explicit compiler CLI boundaries.
    frozen: Path, lifecycle: Path, dispatches: Path, journal: Path, entry: dict[str, Any], before: str, after: str, output: Path, *workspace: str
) -> None:
    """Run the frozen compiler with the source and workspace observations declared for this worker."""
    captures = {"before": before, "after": after}
    for phase, observation in entry["dispatch"].get("audit_observations", {}).items():
        # Preserve the fixture's actual earlier observations, never dispatch expectations.
        manifest = json.loads(Path(captures[phase]).read_bytes())
        persist_capture(manifest, Path(observation["capture_path"]))
        captures[phase] = observation["capture_path"]
    _cli(
        frozen,
        "compile-node",
        "--input",
        str(lifecycle),
        "--dispatches",
        str(dispatches),
        "--journal",
        str(journal),
        "--node-id",
        entry["node_id"],
        "--before-capture",
        captures["before"],
        "--after-capture",
        captures["after"],
        "--output",
        str(output),
        *workspace,
    )
