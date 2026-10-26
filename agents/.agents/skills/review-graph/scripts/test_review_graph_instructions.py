"""Oversized full-text guidance and owner-authorized separation on matched graphs."""

import json
import shlex
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from review_graph_instructions import CHUNK_BYTES, instruction_context, read_chunk
from review_graph_integrity import digest_bytes
from review_graph_plan import ReviewRequirement, ValidationRequirement, WorkerBudget, WorkerNode, plan_graph
from review_graph_read_provenance import MissingReadProvenanceError
from review_graph_receipts import stage_receipt
from test_review_graph_runtime import SKILL_ROOT
from test_review_graph_transitions import _payload

RULES = (
    "Rule: Parse nonnegative counts; reject negative counts.\n",
    "Applicability: This applies to every src/*.py input boundary.\n",
    "Command: Run just check before delivery.\n",
    "Obligation: Preserve original regression inputs and assertions.\n",
    "Science: Preserve detailed balance; do not substitute rejection for supported success.\n",
    "Ownership: The researcher owns scientific conclusions; do not draft them.\n",
)


def _fixture(root: Path, *, reduced: bool) -> dict[str, Any]:
    root.mkdir()
    historical = []
    for index, rule in enumerate(RULES):
        path = root / f"guidance-{index}.md"
        path.write_text(rule + ("Historical rationale; no additional normative obligations.\n" * 580))
        historical.append(str(path))
    entry = root / "AGENTS.md"
    if reduced:
        entry.write_text(
            "# Consumer-owned instruction entry point\n\n"
            "The instruction owner authorizes execution.md as the complete execution view.\n"
            "Read execution.md in full. guidance-*.md retains the original historical context;\n"
            "it need not be reread unless investigating rationale. Every applicable rule,\n"
            "command, obligation, scientific and authorship constraint is retained verbatim.\n"
        )
        execution = root / "execution.md"
        execution.write_text("".join(RULES))
        instructions = (str(entry), str(execution))
    else:
        entry.write_text("# Consumer-owned instruction entry point\n\nRead every guidance-*.md in full before work, including after compaction.\n")
        instructions = (str(entry), *historical)
    skill = SKILL_ROOT / "python-parse-dont-validate/SKILL.md"
    requirements = []
    for index in range(42):
        source = f"src/input_{index}.py"
        path = root / source
        path.parent.mkdir(exist_ok=True)
        path.write_text("def count(value):\n    return int(value)\n")
        requirements.append(
            ReviewRequirement(
                requirement_id=f"boundary-{index}",
                skill_id="python-parse-dont-validate",
                skill_path=str(skill),
                skill_digest=digest_bytes(skill.read_bytes()),
                router_id="python-review-orchestrator",
                rule_id="input-contract",
                review_surface=(source,),
                reason="Each fixture has an independently owned boundary.",
                priority="supporting-quality",
                required=True,
                synthesis_dependency="repository-synthesis",
                instruction_paths=instructions,
            )
        )
    synthesis_skill = SKILL_ROOT / "repository-production-review/SKILL.md"
    validator_skill = SKILL_ROOT / "review-validator/SKILL.md"
    state = ("scope", "worktree", "repository")
    plan = plan_graph(
        requirements,
        [
            ValidationRequirement(
                requirement_id="baseline",
                source_state=state,
                commands=("true",),
                working_directories=(str(root),),
                environment="scripted fixture",
                toolchain="fixture",
                features=(),
                platform="current host",
                artifact_owner="repository",
                mutation_lock="serial",
                baseline=True,
            )
        ],
        [
            WorkerNode(
                node_id="repository-synthesis",
                skill_id="repository-production-review",
                skill_path=str(synthesis_skill),
                skill_digest=digest_bytes(synthesis_skill.read_bytes()),
                mode="synthesis",
                priority="required-routing-synthesis",
                required=True,
                instruction_paths=instructions,
            )
        ],
        validator_skill_path=str(validator_skill),
        validator_skill_digest=digest_bytes(validator_skill.read_bytes()),
        budget=WorkerBudget(50, 1),
        repository_root=root,
    )
    return {
        "plan": json.loads(json.dumps(asdict(plan))),
        "source_state": list(state),
        "repository_root": str(root),
        "authorization": "review-only",
        "state_verification_command": "synthetic-fixture-identity",
        "artifact_store": str(root.parent / (root.name + "-artifacts")),
    }


def _read_context(context: dict[str, Any]) -> dict[str, bytes]:
    reference = context["manifest"]
    manifest = json.loads(Path(reference["path"]).read_bytes())
    return {
        item["path"]: b"".join(read_chunk(Path(reference["path"]), reference["digest"], item["path"], index) for index in range(len(item["chunks"])))
        for item in manifest["files"]
    }


def test_matched_44_node_corpora_measure_bytes_and_preserve_scripted_outcomes(tmp_path: Path) -> None:
    reports = {}
    outcomes = {}
    for mode in ("full", "authorized"):
        request = _fixture(tmp_path / mode, reduced=mode == "authorized")
        start = time.perf_counter()
        result = runtime.materialize_dispatches(request)
        materialization_seconds = time.perf_counter() - start
        assert len(result["dispatches"]) == 44
        demand = result["telemetry"]["instruction_demand"]
        assert demand["repeated_bytes"] == demand["planned_bytes"] - demand["unique_bytes"]
        assert result["telemetry"]["source_demand"]["planned_source_bytes"] > 0
        assert result["telemetry"]["protocol_read_demand"]["planned_bytes"] > 0
        assert demand["provider_tokens"] is None
        assert demand["observed_model_reads"] is None
        start = time.perf_counter()
        delivered = 0
        outcomes[mode] = []
        for entry in result["dispatches"]:
            context = entry["dispatch"]["instruction_context"]
            texts = _read_context(context)
            delivered += sum(len(content) for content in texts.values())
            assert all(content == Path(path).read_bytes() for path, content in texts.items())
            if entry["dispatch"]["mode"] != "audit":
                continue
            assert all(rule.encode() in b"".join(texts.values()) for rule in RULES)
            dispatch = entry["dispatch"]
            payload = _payload(dispatch["owned_paths"], dispatch=dispatch)
            payload.update(
                status="completed",
                findings=[
                    {
                        "severity": "P2",
                        "location": dispatch["owned_paths"][0] + ":2",
                        "summary": "Negative counts are accepted",
                        "evidence": "Scripted fixture finding: int(-1) remains negative.",
                        "remediation": "Reject negative counts at parsing.",
                    }
                ],
            )
            _content, metadata = runtime.compile_review(
                {"dispatch": {**dispatch, "before_state": request["source_state"], "after_state": request["source_state"]}, "payload": payload}
            )
            outcomes[mode].append(metadata["normalized_record"]["findings"])
        assert delivered == demand["planned_bytes"]
        reports[mode] = {
            "instruction_bytes": {key: demand[key] for key in ("unique_bytes", "planned_bytes", "repeated_bytes")},
            "materialization_seconds": materialization_seconds,
            "scripted_read_and_compile_seconds": time.perf_counter() - start,
            "scripted_findings": len(outcomes[mode]),
            "model_coverage_equivalence": None,
        }
        output = tmp_path / (mode + ".json")
        output.write_text(json.dumps(result))
        receipt = stage_receipt("materialize-dispatches", output, result)
        assert receipt["instruction_preflight"]["large_corpus"] == (mode == "full")
        if mode == "full":
            assert 190_000 < demand["unique_bytes"] < 220_000
            assert demand["planned_bytes"] > 8_000_000
    assert outcomes["full"] == outcomes["authorized"]
    for index in range(len(RULES)):
        assert (tmp_path / "full" / f"guidance-{index}.md").read_bytes() == (tmp_path / "authorized" / f"guidance-{index}.md").read_bytes()
    (tmp_path / "measurements.json").write_text(json.dumps(reports, indent=2))


def test_fresh_or_compacted_context_requires_text_and_does_not_attest_from_disk(tmp_path: Path) -> None:
    result = runtime.materialize_dispatches(_fixture(tmp_path / "full", reduced=False))
    entry = next(item for item in result["dispatches"] if item["dispatch"]["mode"] == "audit")
    view = json.loads(Path(entry["worker_execution_path"]).read_bytes())
    context = view["dispatch"]["instruction_context"]
    assert context["model_availability"] == "unknown"
    # A fresh reader can recover all original text without the previous model state.
    assert set(_read_context(context)) == set(entry["dispatch"]["instruction_paths"])
    assert context["model_availability"] == "unknown"
    payload = _payload(entry["dispatch"]["owned_paths"])
    dispatch = {**entry["dispatch"], "before_state": result["source_state"], "after_state": result["source_state"]}
    with pytest.raises(MissingReadProvenanceError):
        runtime.compile_review({"dispatch": dispatch, "payload": payload})
    payload["nearby_contract_owners"] = dispatch["required_read_paths"]
    path = dispatch["instruction_paths"][0]
    command = shlex.join([*context["read_command"], "--path", path, "--chunk", "0"])
    payload["commands_executed"] = [command]
    _content, metadata = runtime.compile_review({"dispatch": dispatch, "payload": payload})
    assert command in metadata["normalized_record"]["protocol_commands"]


@pytest.mark.parametrize("damage", [None, "live", "snapshot", "manifest"])
def test_bounded_reader_is_lossless_and_rejects_changed_identities(tmp_path: Path, damage: str | None) -> None:
    path = tmp_path / "unicode.md"
    original = ("Scientific λ🙂 " * 4000 + "\nlast line").encode()
    path.write_bytes(original)
    context, writes = instruction_context((str(path),), tmp_path)
    for target, content in writes.items():
        target.write_bytes(content)
    reference = context["manifest"]
    manifest = json.loads(Path(reference["path"]).read_bytes())
    chunks = manifest["files"][0]["chunks"]
    assert all(end - start <= CHUNK_BYTES for start, end in chunks)
    if damage is None:
        assert _read_context(context)[str(path)] == original
        assert all(original[start:end].decode("utf-8") for start, end in chunks)
        return
    target = path if damage == "live" else Path(manifest["files"][0]["snapshot_path"] if damage == "snapshot" else reference["path"])
    target.write_bytes(b"changed")
    with pytest.raises(ValueError, match=r"identity changed|digest mismatch"):
        read_chunk(Path(reference["path"]), reference["digest"], str(path), 0)
