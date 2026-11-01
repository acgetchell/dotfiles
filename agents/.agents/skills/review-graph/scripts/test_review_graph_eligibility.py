"""Publication diagnostics and actual reuse across a staged lockfile update."""

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_eligibility import compact_eligibility, reuse_eligibility
from review_graph_plan import plan_from_document
from review_graph_read_provenance import bind_runtime_reads
from review_graph_session import freeze_runtime
from test_review_graph_runtime import ROUTING_CATALOG, SKILL_ROOT, _baseline_mutation_fixture, _complete_structural_fixture_routing, _run_test_git
from test_review_graph_transitions import _materialize, _payload


def _execute_reads(repository: Path, commands: list[str]) -> None:
    shell = shutil.which("bash")
    assert shell is not None
    for command in commands:
        subprocess.run([shell, "-c", command], cwd=repository, check=True, capture_output=True)  # noqa: S603 - exact fixture-owned read commands.


def test_frozen_framework_inspections_bind_only_exact_verified_resources(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    reference = freeze_runtime(SKILL_ROOT, tmp_path / "runtime", repository=repository)
    helper = str(Path(reference["path"]).parent / "skills/review-graph/scripts/review_graph_reads.py")
    commands = [shlex.join(["cat", helper]) + "\n" + shlex.join(["cat", reference["path"]])]
    _execute_reads(repository, commands)
    dispatch = {"repository_root": str(repository), "runtime_snapshot": reference}
    payload = {"commands_executed": commands}
    bindings, protocol = bind_runtime_reads(dispatch, payload)
    assert set(dict(bindings)) == {helper, reference["path"]}
    assert not protocol  # Readers stay readers; only their external identities are bound.
    assert reuse_eligibility({**payload, "runtime_inputs": bindings}, str(repository))["status"] == "no-known-ledger-blockers"
    helper_path = Path(helper)
    helper_path.chmod(0o644)
    helper_path.write_text("changed frozen helper\n")
    with pytest.raises(ValueError, match=r"frozen runtime resource changed: skills/review-graph/scripts/review_graph_reads\.py"):
        bind_runtime_reads(dispatch, payload)


def test_compact_diagnostic_points_to_exact_entries_without_rewriting_them(tmp_path: Path) -> None:
    commands = [f"Inspected contract {index}: " + "details " * 100 for index in range(12)]
    record = {"commands_executed": commands.copy()}
    diagnostic = reuse_eligibility(record, str(tmp_path))
    compact = compact_eligibility(diagnostic)
    assert compact["blocker_count"] == 12
    assert compact["omitted_blockers"] == 4
    assert len(compact["blockers"]) == 8
    assert len(compact["blockers"][0]["command"]) == 240
    assert diagnostic["blockers"][0]["command"] == commands[0]
    assert diagnostic["blockers"][0]["command_entries"] == [1]
    assert record["commands_executed"] == commands


def test_compact_external_read_truncates_only_the_diagnostic(tmp_path: Path) -> None:
    external = str(tmp_path / ("outer" * 25) / ("inner" * 25) / "external.txt")
    commands = [shlex.join(["cat", external])]
    record = {"commands_executed": commands.copy()}
    assert len(external) > 240

    diagnostic = reuse_eligibility(record, str(tmp_path / "repository"))
    compact = compact_eligibility(diagnostic)

    assert compact["blockers"] == [{"reason_code": "unbound-external-read", "path": external[:240]}]
    assert diagnostic["blockers"] == [{"reason_code": "unbound-external-read", "path": external}]
    assert record["commands_executed"] == commands


@pytest.mark.parametrize("context", ["proved", "unknown-command", "external-read", "uncertain"])
def test_baseline_reports_blockers_before_accepting_and_preserves_only_proved_audits(  # noqa: C901, PLR0915 - complete lifecycle regression.
    tmp_path: Path, capsys: pytest.CaptureFixture[str], context: str
) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    locks = ("Cargo.lock", "uv.lock")
    for path in locks:
        (repository / path).write_text('version = "1"\n', encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "add", *locks)
    _run_test_git(git, "-C", str(repository), "commit", "-m", "fixture locks")
    capture = _scope_data(git, repository, "baseline", None, ())
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    lifecycle_path, capture_path, journal = (tmp_path / name for name in ("lifecycle.json", "capture.json", "journal.jsonl"))
    lifecycle_path.write_text(json.dumps(lifecycle))
    capture_path.write_text(json.dumps(capture))
    protected: dict[Path, bytes] = {}
    expected_preserved = set()
    expected_recheck = set()
    target_id = ""
    for entry in entries["dispatches"]:
        dispatch = entry["dispatch"]
        if dispatch["mode"] != "audit":
            continue
        payload = _payload(dispatch["owned_paths"], dispatch=dispatch)
        if dispatch["skill_id"] == "rust-build-portability":
            payload["nearby_contract_owners"].extend(locks)
        shared = dispatch["shared_inspection_evidence"]
        framework = [entry["worker_input_path"], entry["worker_execution_path"], shared["artifact_path"], shared["source_packet_path"]]
        commands = [
            "sed -n '1,80p' tool.py\nsed -n '1,80p' state.rs",
            "\n".join(shlex.join(["cat", "--", path]) for path in [*payload["files_inspected"], *payload["nearby_contract_owners"], *framework]),
        ]
        target = dispatch["skill_id"] == "python-cli-review"
        if target:
            target_id = entry["node_id"]
            if context == "unknown-command":
                commands.append(shlex.join([sys.executable, "-c", "pass # " + "long diagnostic " * 20]))
            elif context == "external-read":
                external = tmp_path / "external.txt"
                external.write_text("unbound context\n")
                commands.append(shlex.join(["cat", str(external)]))
                payload["nearby_contract_owners"].append(str(external))
            elif context == "uncertain":
                payload["unresolved_uncertainties"] = [{"kind": "dependency", "reason": "Dynamic configuration inputs remain uncertain."}]
        _execute_reads(repository, commands)
        payload["commands_executed"] = commands
        contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
        receipt = runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
        diagnostic = runtime._worker_payload_cli_output(receipt, full_output=False)["reuse_eligibility"]
        if target and context in {"unknown-command", "external-read"}:
            code = "unclassified-command" if context == "unknown-command" else "unbound-external-read"
            assert diagnostic["status"] == "blocked"
            assert diagnostic["reason_counts"] == {code: 1}
            field, expected = ("command", commands[-1]) if context == "unknown-command" else ("path", str(tmp_path / "external.txt"))
            assert diagnostic["blockers"][0][field] == expected[:240]
        else:
            assert diagnostic["status"] == "no-known-ledger-blockers"
        # Publication exposes this before compile-node accepts the audit.
        output = tmp_path / f"{entry['node_id']}.compiled.json"
        arguments = {
            "input": lifecycle_path,
            "dispatches": dispatches,
            "journal": journal,
            "node-id": entry["node_id"],
            "before-capture": capture_path,
            "after-capture": capture_path,
            "output": output,
        }
        assert runtime.main(["compile-node", *(arg for key, value in arguments.items() for arg in (f"--{key}", str(value)))]) == 0
        compiled = json.loads(capsys.readouterr().out)
        assert compiled["status"] == "accepted"
        assert compiled["reuse_eligibility"] == diagnostic
        metadata = json.loads(Path(entry["metadata_path"]).read_bytes())
        assert metadata["normalized_record"]["commands_executed"] == commands
        assert all(path in dict(metadata["normalized_record"]["runtime_inputs"]) for path in framework)
        for path in [entry["artifact_path"], entry["metadata_path"], metadata["worker_payload_path"]]:
            protected[Path(path)] = Path(path).read_bytes()
        blocked = bool(set(dispatch["owned_paths"]) & set(locks)) or dispatch["skill_id"] == "rust-build-portability" or (target and context != "proved")
        (expected_recheck if blocked else expected_preserved).add(entry["node_id"])
    assert target_id
    assert expected_preserved
    assert expected_recheck
    for path in locks:
        (repository / path).write_text('version = "2"\n', encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "add", *locks)
    index = (repository / ".git/index").read_bytes()
    result = runtime.resume_after_external_source(
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "dispatches_path": str(dispatches),
            "journal_path": str(journal),
            "artifact_store": str(tmp_path / "resumed"),
            "external_source_actor": "maintainer",
            "external_source_attribution": "The maintainer updated both lockfiles.",
            "external_staging_attribution": "The maintainer confirmed staging both locks.",
        }
    )
    assert set(result["preserved_node_ids"]) == expected_preserved
    assert expected_recheck <= set(result["recheck_node_ids"])
    assert result["lifecycle_input"]["plan"]["review_lifecycle"] == lifecycle["plan"]["review_lifecycle"]
    assert all(path.read_bytes() == content for path, content in protected.items())
    assert (repository / ".git/index").read_bytes() == index
