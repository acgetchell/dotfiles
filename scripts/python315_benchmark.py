"""Measure JIT costs on the canonical planner and publication fixture."""

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from research_repo_tools.selection import select_files

REPOSITORY = Path(__file__).resolve().parents[1]
GRAPH = REPOSITORY / "agents/.agents/skills/review-graph/scripts"


def outside_repository(path: Path) -> Path:
    """Resolve symlinks before admitting an artifact or fixture destination."""
    resolved = path.resolve()
    if resolved.is_relative_to(REPOSITORY):
        msg = "benchmark artifacts and fixtures must be outside the repository"
        raise ValueError(msg)
    return resolved


def runtime_identity() -> dict[str, object]:
    """Retain allowlisted build/platform/dependency facts without ambient secrets."""
    return {
        "executable": sys.executable,
        "implementation": sys.implementation.name,
        "version": sys.version,
        "build": list(platform.python_build()),
        "compiler": platform.python_compiler(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "dependencies": {name: importlib.metadata.version(name) for name in ("research-repo-tools", "PyYAML", "packaging")},
    }


def source_identity() -> str:
    """Hash selected source bytes without changing repository or Git state."""
    digest = hashlib.sha256()
    for name in select_files(REPOSITORY):
        digest.update(name.encode() + b"\0" + (REPOSITORY / name).read_bytes() + b"\0")
    return digest.hexdigest()


def worker(root: Path, output: Path, scale: int) -> dict[str, Any]:
    """Prepare outside timing, then measure cold and warm real domain operations."""
    if scale < 1:
        msg = "scale must be positive"
        raise ValueError(msg)
    root, output = outside_repository(root), outside_repository(output)
    for directory in (root, output):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Fresh private subtrees keep fixture and sidecar writes away from existing links.
    root = Path(tempfile.mkdtemp(prefix="fixture-", dir=root))
    output = Path(tempfile.mkdtemp(prefix="replays-", dir=output))
    sys.path.insert(0, str(GRAPH))
    benchmark = importlib.import_module("review_graph_benchmark")
    runtime = importlib.import_module("review_graph_runtime")
    planner = benchmark.plan_graph
    invocation: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def capture(*args: Any, **kwargs: Any) -> Any:
        invocation.append((args, kwargs))
        return planner(*args, **kwargs)

    # Reuse the fixture's exact planner inputs rather than inventing another workload.
    benchmark.__dict__["plan_graph"] = capture
    try:
        document = benchmark.benchmark_fixture(root / "repository", scale=scale)
    finally:
        benchmark.__dict__["plan_graph"] = planner
    if len(invocation) != 1:
        msg = "canonical fixture must provide exactly one planner invocation"
        raise ValueError(msg)
    args, kwargs = invocation[0]
    plan_samples = []
    for index in range(21):
        started = time.perf_counter()
        plan = planner(*args, **kwargs)
        elapsed = time.perf_counter() - started
        if index:
            plan_samples.append(elapsed)
    replay_samples = []
    expected_findings = None
    for index in range(4):
        trial = benchmark._trial(runtime, document, output / f"trial-{index}")  # noqa: SLF001 - canonical owned benchmark boundary.
        findings = trial["findings"]
        if len(findings) != 4 or (expected_findings is not None and findings != expected_findings):
            msg = "protocol replay changed the seeded findings"
            raise ValueError(msg)
        expected_findings = findings
        replay_samples.append(trial["metrics"]["total_seconds"])
    jit = getattr(sys, "_jit", None)
    return {
        "python": sys.version,
        "environment": runtime_identity(),
        "pid": os.getpid(),
        "jit_available": jit is not None and jit.is_available(),
        "jit_enabled": jit is not None and jit.is_enabled(),
        "planner_seconds": plan_samples,
        "cold_replay_seconds": replay_samples[0],
        "warm_replay_seconds": replay_samples[1:],
        "seeded_findings": len(expected_findings or []),
        "findings": expected_findings,
        "nodes": len(plan.actual_worker_nodes),
    }


def summary(samples: list[float]) -> dict[str, object]:
    """Retain raw samples plus median and robust dispersion."""
    median = statistics.median(samples)
    return {"samples_seconds": samples, "median_seconds": median, "mad_seconds": statistics.median(abs(sample - median) for sample in samples)}


def trial_metrics(trial: dict[str, Any]) -> dict[str, float]:
    """Weight every subprocess equally, including its internal warm samples."""
    return {
        "planner": statistics.median(trial["planner_seconds"]),
        "cold_replay": trial["cold_replay_seconds"],
        "warm_replay": statistics.median(trial["warm_replay_seconds"]),
        "whole_process": trial["process_seconds"],
    }


def paired_effects(off: list[dict[str, Any]], on: list[dict[str, Any]]) -> dict[str, object]:
    """Retain within-pair JIT differences and dimensionless ratios."""
    pairs = [(trial_metrics(before), trial_metrics(after)) for before, after in zip(off, on, strict=True)]
    effects = {}
    for metric in pairs[0][0]:
        if any(before[metric] <= 0 or after[metric] <= 0 for before, after in pairs):
            msg = "benchmark measurements must be positive"
            raise ValueError(msg)
        ratios = [after[metric] / before[metric] for before, after in pairs]
        median = statistics.median(ratios)
        effects[metric] = {
            "on_minus_off": summary([after[metric] - before[metric] for before, after in pairs]),
            "on_over_off": {"samples": ratios, "median": median, "mad": statistics.median(abs(ratio - median) for ratio in ratios)},
        }
    return effects


def write_worker_logs(directory: Path, stdout: str | bytes | None, stderr: str | bytes | None) -> None:
    """Keep worker diagnostics private, including partial timeout output."""
    for name, value in (("stdout", stdout), ("stderr", stderr)):
        data = value.encode("utf-8") if isinstance(value, str) else value or b""
        (directory / f"worker.{name}").write_bytes(data)


def run(output: Path, repeats: int, scale: int) -> dict[str, Any]:
    """Alternate isolated JIT modes and verify source/semantic preservation."""
    if repeats < 2 or scale < 1:
        msg = "repeats must be at least two and scale must be positive"
        raise ValueError(msg)
    output = outside_repository(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    before = source_identity()
    trials: dict[str, list[dict[str, Any]]] = {"off": [], "on": []}
    pair_order = []
    for index in range(repeats):
        modes = ("off", "on") if index % 2 == 0 else ("on", "off")
        pair_order.append({"pair_index": index, "modes": list(modes)})
        for mode in modes:
            store = output / f"{mode}-{index}"
            store.mkdir(mode=0o700)
            started = time.perf_counter()
            try:
                result = subprocess.run(  # noqa: S603 - fixed local worker, explicit mode and private artifact directory.
                    [sys.executable, str(Path(__file__).resolve()), "--worker", "--output", str(store), "--fixture-root", str(output), "--scale", str(scale)],
                    cwd=REPOSITORY,
                    env={**os.environ, "PYTHON_JIT": "1" if mode == "on" else "0"},
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=180,
                )
            except subprocess.TimeoutExpired as error:
                write_worker_logs(store, error.stdout, error.stderr)
                msg = f"JIT {mode} worker timed out; diagnostics: {store}"
                raise ValueError(msg) from error
            process_seconds = time.perf_counter() - started
            write_worker_logs(store, result.stdout, result.stderr)
            if result.returncode:
                msg = f"JIT {mode} worker exited {result.returncode}; diagnostics: {store}"
                raise ValueError(msg)
            trial = json.loads(result.stdout)
            if not trial["jit_available"] or trial["jit_enabled"] != (mode == "on"):
                msg = "interpreter did not honor the requested JIT mode"
                raise ValueError(msg)
            trial["process_seconds"] = process_seconds
            trial["pair_index"] = index
            trials[mode].append(trial)
        if trials["off"][-1]["findings"] != trials["on"][-1]["findings"]:
            msg = "JIT modes changed compiled findings"
            raise ValueError(msg)
    if before != source_identity():
        msg = "source changed during benchmark"
        raise ValueError(msg)
    report = {
        "schema_version": 2,
        "source_sha256": before,
        "repeats": repeats,
        "scale": scale,
        "pair_order": pair_order,
        "paired": paired_effects(trials["off"], trials["on"]),
        "results": {
            mode: {**{metric: summary([trial_metrics(trial)[metric] for trial in samples]) for metric in trial_metrics(samples[0])}, "trials": samples}
            for mode, samples in trials.items()
        },
        "limits": "Sequential alternating subprocesses on one interpreter/build. Planner setup and imports are excluded from operation times; "
        "whole-process times include imports, fixture preparation, and cold/warm operations. No model work, live validators, or Git mutations. "
        "Four seeded findings prove preservation, not discovery quality. JIT is queried only after timed operations.",
    }
    # Machine paths remain in private replay artifacts; the shareable summary uses placeholders.
    portable = json.dumps(report, indent=2, sort_keys=True).replace(str(REPOSITORY), "$REPO").replace(str(output), "$RUN").replace(str(Path.home()), "$HOME")
    (output / "report.json").write_text(portable + "\n", encoding="utf-8")
    return report


def main() -> int:
    """Expose a bounded benchmark and its internal subprocess worker."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--scale", type=int, default=20)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--fixture-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker and (args.output is None or args.fixture_root is None):
        parser.error("worker requires output and fixture root")
    try:
        if args.worker:
            print(json.dumps(worker(args.fixture_root, args.output, args.scale)))
            return 0
        output = args.output or Path(tempfile.mkdtemp(prefix="dotfiles-python315-")) / "results"
        report = run(output, args.repeats, args.scale)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"python315-benchmark: {error}", file=sys.stderr)
        return 1
    for mode, result in report["results"].items():
        print(f"JIT {mode}: planner {result['planner']['median_seconds']:.6f}s; warm replay {result['warm_replay']['median_seconds']:.6f}s")
    print(output / "report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
