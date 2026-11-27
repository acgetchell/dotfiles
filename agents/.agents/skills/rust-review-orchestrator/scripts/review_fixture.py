"""Measure standalone Rust instruction delivery and validate source separately."""

import argparse
import json
import shutil
import subprocess
import tempfile
from functools import partial
from pathlib import Path
from typing import Any

from instruction_receipt import MAX_CHUNK_BYTES, deliver_instructions, digest

SCRIPT = Path(__file__).resolve().parent
SKILLS = SCRIPT.parents[1]
REPOSITORY = SKILLS.parents[2]
BASELINE = "fa7231d431db9d6207bed98be0e719d085a700bf"
SCOPE = "warmup-fixture:whole-repository"
OVERSIZED_VIEW = [
    f"{skill}/SKILL.md"
    for skill in (
        "rust-fluent-api-design",
        "rust-trait-bounds",
        "rust-invariant-state-transitions",
        "rust-parse-dont-validate",
        "rust-error-variants",
        "rust-borrowed-view-audit",
    )
]
SELECTED = [
    "rust-cargo-hygiene",
    "project-tooling-review",
    "rust-api-design",
    "rust-api-docs",
    "rust-prelude-exports",
    "rust-fluent-api-design",
    "rust-trait-bounds",
    "rust-invariant-state-transitions",
    "rust-parse-dont-validate",
    "rust-error-variants",
    "rust-scientific-correctness",
    "rust-invariant-performance",
    "rust-test-quality",
    "rust-production-review",
]
SKIPPED = {
    "rust-build-portability": "No changed feature, target, cfg, build script, or external linking contract",
    "rust-cli-design": "Example only; no argument or process interface",
    "rust-borrowed-view-audit": "No snapshot, cache, borrowed-view, or provenance change",
    "rust-concurrency-async": "Synchronous deterministic kernel",
    "rust-style-hygiene": "No material naming/import concern",
    "rust-iter-control-flow": "No separate iterator-contract change; transition loop belongs to state/performance",
    "rust-simplification-review": "No requested simplification or duplicate API migration",
}
REFERENCES = {
    "project-tooling-review": ["references/justfile.md", "references/tool-versions.md"],
    "rust-parse-dont-validate": ["references/nonzero-numeric-refinements.md"],
    "rust-invariant-performance": ["references/benchmark-evidence.md"],
}


def run(command: list[str], cwd: Path) -> str:
    """Capture a checked local command without shell interpretation."""
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=True, timeout=120).stdout  # noqa: S603


def instruction_paths(skill: str, *, baseline: bool) -> list[str]:
    """Return this controlled fixture's applicable bodies and references."""
    paths = [f"{skill}/SKILL.md", *(f"{skill}/{name}" for name in REFERENCES.get(skill, []))]
    if baseline and skill == "project-tooling-review":
        paths.append(f"{skill}/references/standalone-workflow.md")
    return paths


def prepare_baseline(output: Path, revision: str) -> Path:
    """Read immutable baseline documents without changing repository Git state."""
    root = output / "baseline-skills"
    paths = {"rust-review-orchestrator/SKILL.md", "rust-review-orchestrator/references/check-routing.md"}
    for skill in SELECTED:
        paths.update(instruction_paths(skill, baseline=True))
    for name in sorted(paths):
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "show", f"{revision}:agents/.agents/skills/{name}"]
        content = subprocess.run(command, cwd=REPOSITORY, capture_output=True, check=True, timeout=120).stdout  # noqa: S603
        destination.write_bytes(content)
    return root


def receive_view(
    root: Path, paths: list[str], ledger: dict[str, Any], *, skill_id: str, interrupt: bool = False
) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    """Collect a full view and optionally retry a delivery after the first acknowledgement."""
    step = partial(deliver_instructions, root, paths, context="fixture", scope=SCOPE, skill_id=skill_id)
    delivery, ledger, receipt = step(ledger)
    text = bytearray()
    chunk_sizes: list[int] = []
    interrupted = None
    while delivery is not None:
        if interrupt and interrupted is None and receipt["files"][0]["status"] == "loaded":
            response = delivery.render()
            truncated_response = response[: len(response) // 2]
            interrupted = {"response_bytes": len(truncated_response), "receipt": receipt}
            retried, ledger, receipt = step(ledger)
            if retried != delivery:
                raise ValueError("Retry did not reproduce the unacknowledged delivery")  # noqa: EM101
        if delivery.start == 0:
            if text:
                text.extend(b"\n")
            text.extend(f"<!-- {delivery.path} sha256={delivery.sha256} -->\n".encode())
        text.extend(delivery.content)
        chunk_sizes.append(len(delivery.content))
        delivery, ledger, receipt = step(ledger, ack=delivery.token)
    return bytes(text), ledger, {**receipt, "chunk_sizes": chunk_sizes, "interrupted": interrupted}


def measure(root: Path, output: Path, *, baseline: bool) -> dict[str, Any]:
    """Actually read/emit fixture instructions, then replay an unchanged revisit."""
    ledger: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    paths = ["rust-review-orchestrator/SKILL.md", "rust-review-orchestrator/references/check-routing.md"]
    if not baseline:
        paths.append("rust-review-orchestrator/references/execution-v1.md")
    batches = [("parent", paths), *((skill, instruction_paths(skill, baseline=baseline)) for skill in SELECTED)]
    for cycle in range(2):
        for skill, required in batches:
            # Legacy full-body loading is deliberately replayed for the controlled revisit.
            prior = {} if baseline else ledger
            text, ledger, receipt = receive_view(root, required, prior, skill_id=skill)
            (output / f"{cycle}-{skill}.txt").write_bytes(text)
            for row in receipt["files"]:
                key = (row["path"], row["sha256"])
                row["reread"] = row["status"] == "loaded" and key in seen
                if row["status"] == "loaded":
                    seen.add(key)
            events.append({"cycle": cycle, **receipt})
    loaded = [row for event in events for row in event["files"] if row["status"] == "loaded"]
    return {
        "first_load_bytes": sum(row["bytes"] for row in loaded if not row["reread"]),
        "reread_bytes": sum(row["bytes"] for row in loaded if row["reread"]),
        "body_bytes": sum(row["bytes"] for row in loaded if row["path"].endswith("SKILL.md")),
        "reference_bytes": sum(row["bytes"] for row in loaded if not row["path"].endswith("SKILL.md")),
        "events": events,
    }


def measure_resumable_delivery(root: Path, output: Path, *, original_source: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replay the oversized review and test source evidence identity across a repair."""
    skill_id = "api-state-errors-and-borrowing"
    text, ledger, first = receive_view(root, OVERSIZED_VIEW, {}, skill_id=skill_id, interrupt=True)
    (output / "oversized-view.txt").write_bytes(text)
    _, ledger, repeat = receive_view(root, OVERSIZED_VIEW, ledger, skill_id=skill_id)
    repaired = output / "repaired"
    repaired.mkdir()
    prepare_repaired_source(repaired / "source")
    repaired_source = validate_source(repaired, repaired / "source")
    _, _, after_repair = receive_view(root, OVERSIZED_VIEW, ledger, skill_id=skill_id)
    repaired_fingerprint = repaired_source["source_sha256"]
    interrupted = first.pop("interrupted")
    report = {
        "scope": SCOPE,
        "context": "fixture",
        "authorization": "Review the supplied fixture and repair the scoped callback defect in its temporary copy",
        "chunk_byte_limit": MAX_CHUNK_BYTES,
        "first_load_bytes": sum(first["chunk_sizes"]),
        "repeat_bytes": sum(repeat["chunk_sizes"]),
        "after_repair_bytes": sum(after_repair["chunk_sizes"]),
        "receipts": {"interrupted": interrupted, "first_load": first, "repeat": repeat, "after_repair": after_repair},
        "source_evidence": {
            "original_source_sha256": original_source,
            "repaired_source_sha256": repaired_fingerprint,
            "original_source_evidence_eligible": original_source == repaired_fingerprint,
        },
    }
    return report, repaired_source


def prepare_repaired_source(source: Path) -> None:
    """Copy the controlled fixture and remove the two discarded callback calls."""
    shutil.copytree(SCRIPT / "fixtures/warmup", source)
    adaptive = source / "src/adaptive.rs"
    adaptive.write_bytes(
        adaptive.read_bytes()
        .replace(b"self.step_mut().outcome", b"self.proposal.transition(&mut self.state)")
        .replace(b"self.step_delayed().outcome", b"self.proposal.transition(&mut self.state)")
    )


def library_artifact(cargo_output: str) -> Path:
    """Find the fixture library from Cargo messages, independent of target layout."""
    libraries = []
    for line in cargo_output.splitlines():
        if not line.startswith("{"):
            continue
        message = json.loads(line)
        if message.get("reason") == "build-finished":
            break
        if message.get("reason") == "compiler-artifact" and message["target"]["name"] == "warmup_fixture":
            libraries.extend(Path(name) for name in message["filenames"] if name.endswith(".rlib"))
    if len(libraries) != 1:
        raise ValueError("Expected one warmup_fixture rlib artifact from Cargo")  # noqa: EM101
    return libraries[0]


def validate_source(output: Path, source: Path = SCRIPT / "fixtures/warmup") -> dict[str, Any]:
    """Run shared source validation and the independent downstream callback probe."""
    fingerprints = {path.relative_to(source).as_posix(): digest(path.read_bytes()) for path in sorted(source.rglob("*")) if path.is_file()}
    source_bytes = sum(path.stat().st_size for path in source.rglob("*") if path.is_file())
    target = output / "target"
    toolchain = run(["rustc", "-vV"], source)
    (host,) = (line.removeprefix("host: ") for line in toolchain.splitlines() if line.startswith("host: "))
    # Both the tests and the separately compiled probe execute on this host.
    command = ["cargo", "test", "--locked", "--offline", "--target", host, "--target-dir", str(target), "--message-format=json"]
    tests = run(command, source)
    (output / "validation.txt").write_text(tests)
    library = library_artifact(tests)
    probe = SCRIPT / "fixtures/callback_probe.rs"
    executable = output / "callback-probe"
    run(["rustc", "--edition=2024", "--target", host, str(probe), "--extern", f"warmup_fixture={library}", "-o", str(executable)], source)
    callbacks = run([str(executable)], source)
    (output / "callbacks.txt").write_text(callbacks)
    return {
        "source_sha256": digest(json.dumps(fingerprints, sort_keys=True).encode()),
        "files": fingerprints,
        "source_read_bytes": source_bytes,
        "probe_bytes": probe.stat().st_size,
        "probe_sha256": digest(probe.read_bytes()),
        "toolchain": toolchain,
        "command": command,
        "cwd": str(source),
        "features": "default (none)",
        "profile": "test/debug",
        "instrumentation": "none; separate callback Cell counter probe",
        "result": "passed",
        "exit_code": 0,
        "validation_artifact": str(output / "validation.txt"),
        "callbacks": callbacks.splitlines(),
    }


def main() -> None:
    """Write byte accounting, source receipts, and complete emitted instructions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="rust-review-fixture-"))
    output.mkdir(exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use an empty output directory")  # noqa: EM101
    baseline = prepare_baseline(output, args.baseline)
    source = validate_source(output)
    report: dict[str, Any] = {"baseline": args.baseline, "selected": SELECTED, "skipped": SKIPPED, "source": source}
    for name, root, legacy in [("before", baseline, True), ("after", SKILLS, False)]:
        destination = output / name
        destination.mkdir()
        report[name] = measure(root, destination, baseline=legacy)
    delivery, repaired_source = measure_resumable_delivery(SKILLS, output, original_source=source["source_sha256"])
    report["resumable_delivery"] = delivery
    report["repaired_source"] = repaired_source
    report["baseline_selected_body_bytes"] = sum((baseline / skill / "SKILL.md").stat().st_size for skill in SELECTED)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    shutil.copytree(SCRIPT / "fixtures/warmup", output / "source")
    handoff = {
        "scope": SCOPE,
        "source_files": source["files"],
        "source_sha256": source["source_sha256"],
        "authorization": "Read-only review; additional focused probes may write only to temporary output",
        "selected": SELECTED,
        "skipped": SKIPPED,
        "required_references": {skill: instruction_paths(skill, baseline=False)[1:] for skill in SELECTED},
        "fingerprint_format": "SHA-256 of UTF-8 json.dumps(source_files, sort_keys=True), with Python's default separators",
        "validation": {key: source[key] for key in ("toolchain", "command", "cwd", "features", "profile", "result", "exit_code", "validation_artifact")},
        "validation_note": "Reuse the passed transition/boundary tests and doctests for unchanged source; add only uncovered evidence",
    }
    (output / "handoff.json").write_text(json.dumps(handoff, indent=2) + "\n")
    print(json.dumps({"output": str(output), **{key: value for key, value in report.items() if key in {"baseline", "baseline_selected_body_bytes"}}}))
    for name in ("before", "after"):
        print(json.dumps({name: {key: value for key, value in report[name].items() if key != "events"}}))
    print(json.dumps({"resumable_delivery": {key: value for key, value in delivery.items() if key != "receipts"}}))


if __name__ == "__main__":
    main()
