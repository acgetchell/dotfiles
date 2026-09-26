"""Replay the issue #84 selection and count emitted instruction bytes separately from source."""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from instruction_receipt import digest, load_instructions

SCRIPT = Path(__file__).resolve().parent
SKILLS = SCRIPT.parents[1]
REPOSITORY = SKILLS.parents[2]
BASELINE = "fa7231d431db9d6207bed98be0e719d085a700bf"
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
        content = run(["git", "show", f"{revision}:agents/.agents/skills/{name}"], REPOSITORY)
        destination.write_text(content)
    return root


def measure(root: Path, output: Path, *, baseline: bool, scope: str) -> dict[str, Any]:
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
            text, ledger, receipt = load_instructions(root, required, prior, context="fixture", scope=scope, skill_id=skill)
            (output / f"{cycle}-{skill}.txt").write_text(text)
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
        report[name] = measure(root, destination, baseline=legacy, scope=source["source_sha256"])
    report["baseline_selected_body_bytes"] = sum((baseline / skill / "SKILL.md").stat().st_size for skill in SELECTED)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    shutil.copytree(SCRIPT / "fixtures/warmup", output / "source")
    handoff = {
        "scope": source["files"],
        "source_sha256": source["source_sha256"],
        "authorization": "Read-only review; additional focused probes may write only to temporary output",
        "selected": SELECTED,
        "skipped": SKIPPED,
        "required_references": {skill: instruction_paths(skill, baseline=False)[1:] for skill in SELECTED},
        "fingerprint_format": "SHA-256 of UTF-8 json.dumps(scope, sort_keys=True), with Python's default separators",
        "validation": {key: source[key] for key in ("toolchain", "command", "cwd", "features", "profile", "result", "exit_code", "validation_artifact")},
        "validation_note": "Reuse the passed transition/boundary tests and doctests for unchanged source; add only uncovered evidence",
    }
    (output / "handoff.json").write_text(json.dumps(handoff, indent=2) + "\n")
    print(json.dumps({"output": str(output), **{key: value for key, value in report.items() if key in {"baseline", "baseline_selected_body_bytes"}}}))
    for name in ("before", "after"):
        print(json.dumps({name: {key: value for key, value in report[name].items() if key != "events"}}))


if __name__ == "__main__":
    main()
