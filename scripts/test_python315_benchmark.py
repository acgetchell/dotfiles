"""Protect benchmark evidence and fail before publishing invalid conclusions."""

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

import python315_benchmark as benchmark

if TYPE_CHECKING:
    from pathlib import Path


def test_canonical_worker_preserves_all_findings_and_separates_warm_samples(tmp_path: Path) -> None:
    """Real planning/publication operations supply evidence without timing thresholds."""
    output = tmp_path / "replays"
    output.mkdir()
    result = benchmark.worker(tmp_path, output, 1)
    assert result["seeded_findings"] == 4
    assert sorted(finding["summary"] for finding in result["findings"]) == [f"Seeded regression {index}" for index in range(4)]
    assert len(result["planner_seconds"]) == 20
    assert len(result["warm_replay_seconds"]) == 3
    assert result["cold_replay_seconds"] > 0
    assert result["nodes"] > 0
    assert result["environment"]["executable"] == sys.executable
    assert result["environment"]["implementation"] == "cpython"
    assert set(result["environment"]["dependencies"]) == {"research-repo-tools", "PyYAML", "packaging"}
    assert result["pid"] > 0
    assert len([path for path in output.glob("replays-*/trial-*") if path.is_dir()]) == 4


@pytest.mark.parametrize(("repeats", "scale"), [(1, 1), (2, 0)])
def test_invalid_workload_does_not_create_artifacts(tmp_path: Path, repeats: int, scale: int) -> None:
    output = tmp_path / "results"
    with pytest.raises(ValueError, match=r"repeats.*scale"):
        benchmark.run(output, repeats, scale)
    assert not output.exists()


def test_checkout_cannot_receive_benchmark_artifacts() -> None:
    output = benchmark.REPOSITORY / "benchmark-results"
    with pytest.raises(ValueError, match="outside the repository"):
        benchmark.run(output, 2, 1)
    assert not output.exists()


@pytest.mark.parametrize("failure", ["findings", "source", "jit"])
def test_invalid_measurements_cannot_publish_a_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    """Semantic drift, source edits, and unavailable JIT are evidence failures."""
    calls = []

    def subprocess_result(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        mode = kwargs["env"]["PYTHON_JIT"] == "1"
        calls.append(mode)
        trial = {
            "jit_available": failure != "jit",
            "jit_enabled": mode,
            "findings": ["changed" if mode and failure == "findings" else "preserved"],
            "planner_seconds": [0.1],
            "cold_replay_seconds": 0.2,
            "warm_replay_seconds": [0.1],
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(trial), "")

    monkeypatch.setattr(benchmark.subprocess, "run", subprocess_result)
    monkeypatch.setattr(benchmark, "source_identity", lambda: "after" if calls and failure == "source" else "before")
    output = tmp_path / "results"
    expected = {"findings": "changed compiled findings", "source": "source changed", "jit": "requested JIT mode"}
    with pytest.raises(ValueError, match=expected[failure]):
        benchmark.run(output, 2, 1)
    assert not (output / "report.json").exists()


def test_summary_preserves_samples_and_robust_dispersion() -> None:
    assert benchmark.summary([1.0, 3.0, 100.0]) == {"samples_seconds": [1.0, 3.0, 100.0], "median_seconds": 3.0, "mad_seconds": 2.0}


@pytest.mark.parametrize("destination", ["fixture", "output", "symlink-fixture", "symlink-output", "scale"])
def test_worker_rejects_invalid_destinations_before_preparing_fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, destination: str) -> None:
    """Exercise direct entry, including symlink traversal, without touching the checkout."""
    repository = tmp_path / "checkout"
    repository.mkdir()
    monkeypatch.setattr(benchmark, "REPOSITORY", repository)
    link = tmp_path / "link"
    link.symlink_to(repository, target_is_directory=True)
    observed_target = link.readlink()
    root = (link if destination.startswith("symlink") else repository) / "fixture" if "fixture" in destination else tmp_path / "fixture"
    output = (link if destination.startswith("symlink") else repository) / "output" if "output" in destination else tmp_path / "output"
    with pytest.raises(ValueError, match="positive" if destination == "scale" else "outside the repository"):
        benchmark.worker(root, output, 0 if destination == "scale" else 1)
    assert list(repository.iterdir()) == []
    assert not (tmp_path / "fixture").exists()
    assert not (tmp_path / "output").exists()
    assert link.is_symlink()
    assert link.readlink() == observed_target
    assert link.samefile(repository)


def test_worker_cli_rejection_is_a_diagnostic_without_file_effects(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local worker and rejected checkout fixture path.
        [sys.executable, benchmark.__file__, "--worker", "--output", str(tmp_path / "output"), "--fixture-root", str(benchmark.REPOSITORY)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("python315-benchmark: ")
    assert "outside the repository" in result.stderr
    assert "Traceback" not in result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("destination", ["fixture", "nested-fixture", "sidecar"])
@pytest.mark.parametrize("relative", [False, True])
def test_worker_preserves_checkout_behind_nested_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, destination: str, *, relative: bool) -> None:
    """Real fixture/replay preparation must preserve caller-controlled descendants."""
    repository = tmp_path / "checkout"
    repository.mkdir()
    (repository / "README.md").write_text("Preserved README.\n")
    (repository / "src").mkdir()
    (repository / "src/module_0.py").write_text("Preserved source.\n")
    before = {path.relative_to(repository): path.read_bytes() for path in repository.rglob("*") if path.is_file()}
    monkeypatch.setattr(benchmark, "REPOSITORY", repository)
    root, output = tmp_path / "fixtures", tmp_path / "replays"
    root.mkdir()
    output.mkdir()
    if destination == "sidecar":
        link, target = output / "trial-0.input.json", repository / "README.md"
    elif destination == "nested-fixture":
        (root / "repository").mkdir()
        link, target = root / "repository/src", repository / "src"
    else:
        link, target = root / "repository", repository
    link.symlink_to(os.path.relpath(target, link.parent) if relative else target, target_is_directory=destination != "sidecar")
    observed_target = link.readlink()

    result = benchmark.worker(root, output, 1)

    assert result["seeded_findings"] == 4
    assert {path.relative_to(repository): path.read_bytes() for path in repository.rglob("*") if path.is_file()} == before
    assert link.is_symlink()
    assert link.readlink() == observed_target
    assert link.samefile(target)


def test_successful_report_records_pairs_identity_and_equal_process_weight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Known process measurements independently establish the serialized report contract."""
    order = []
    values = iter([0.0, 10.0, 20.0, 40.0, 50.0, 90.0, 100.0, 180.0])
    monkeypatch.setattr(benchmark.time, "perf_counter", lambda: next(values))
    monkeypatch.setattr(benchmark, "source_identity", lambda: "unchanged")

    def subprocess_result(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        enabled = kwargs["env"]["PYTHON_JIT"] == "1"
        order.append("on" if enabled else "off")
        pair = (len(order) - 1) // 2
        # Unequal inner sample counts must not change each process's weight.
        trial = {
            "jit_available": True,
            "jit_enabled": enabled,
            "findings": ["preserved"],
            "planner_seconds": [2.0, 4.0, 100.0] if pair == 0 else [8.0],
            "cold_replay_seconds": 6.0 if enabled else 3.0,
            "warm_replay_seconds": [2.0] if enabled else [4.0],
            "environment": {"executable": str(benchmark.REPOSITORY / ".venv/bin/python"), "private_environment": False},
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(trial), "")

    monkeypatch.setattr(benchmark.subprocess, "run", subprocess_result)
    output = tmp_path / "results"
    report = benchmark.run(output, 2, 1)
    assert order == ["off", "on", "on", "off"]
    assert report["pair_order"] == [{"pair_index": 0, "modes": ["off", "on"]}, {"pair_index": 1, "modes": ["on", "off"]}]
    assert report["results"]["off"]["planner"] == {"samples_seconds": [4.0, 8.0], "median_seconds": 6.0, "mad_seconds": 2.0}
    assert report["paired"]["cold_replay"]["on_minus_off"] == {"samples_seconds": [3.0, 3.0], "median_seconds": 3.0, "mad_seconds": 0.0}
    assert report["paired"]["warm_replay"]["on_over_off"] == {"samples": [0.5, 0.5], "median": 0.5, "mad": 0.0}
    assert report["paired"]["whole_process"]["on_minus_off"]["samples_seconds"] == [10.0, -40.0]
    persisted = json.loads((output / "report.json").read_text())
    assert persisted["schema_version"] == 2
    assert persisted["source_sha256"] == "unchanged"
    assert persisted["results"]["on"]["trials"][1]["pair_index"] == 1
    assert persisted["results"]["off"]["trials"][0]["environment"]["executable"] == "$REPO/.venv/bin/python"
    assert len(list(output.glob("*/worker.stdout"))) == 4


@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_worker_failure_retains_diagnostics_without_publishing_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    def fail(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"partial output", stderr=b"worker detail")
        return subprocess.CompletedProcess(argv, 7, "partial output", "worker detail")

    monkeypatch.setattr(benchmark.subprocess, "run", fail)
    monkeypatch.setattr(benchmark, "source_identity", lambda: "unchanged")
    output = tmp_path / "results"
    with pytest.raises(ValueError, match="diagnostics:") as error:
        benchmark.run(output, 2, 1)
    assert "worker detail" not in str(error.value)
    assert (output / "off-0/worker.stdout").read_bytes() == b"partial output"
    assert (output / "off-0/worker.stderr").read_bytes() == b"worker detail"
    assert not (output / "report.json").exists()
