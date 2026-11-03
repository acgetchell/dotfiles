"""Capture batching and diagnostics preserve exact evidence and failure behavior."""

import json
import os
import shutil
import subprocess
import sys
from functools import partial
from typing import TYPE_CHECKING, Any

import capture_scope
import pytest
import review_graph_plan
import review_graph_source_change
from research_repo_tools import git_inspect
from review_graph_capture_timing import collect_timings
from review_graph_commit import verify_live_commit
from review_graph_results import EvaluationBoundaryError, RejectionKind
from test_capture_scope import _capture, _capture_result, _commit_all, _git, _init_repo

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("mode", ["baseline", "branch", "staged", "worktree"])
def test_capture_timings_leave_source_evidence_identical(tmp_path: Path, mode: str) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "source.py").write_bytes(b"original\n")
    _commit_all(repo)
    (repo / "source.py").write_bytes(b"staged\n")
    _git(repo, "add", "source.py")
    (repo / "source.py").write_bytes(b"unstaged\n")
    index = (repo / ".git/index").read_bytes()
    arguments = ("--base", "HEAD") if mode == "branch" else ()
    expected = _capture(repo, mode, *arguments)
    result = _capture_result(repo, mode, *arguments, "--timings")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected
    timing = json.loads(result.stderr)
    assert timing["format"] == "review-graph-capture-timing-v1"
    assert timing["exit_code"] == 0
    assert timing["elapsed_seconds"] > 0
    phases = timing["phases"]
    for name in ("git_discovery", "runtime_verification", "scope_capture", "line_bounds", "repository_state", "git.diff", "git.status"):
        assert phases[name]["calls"] >= 1
        assert phases[name]["elapsed_seconds"] > 0
    assert (repo / ".git/index").read_bytes() == index


def test_failed_capture_reports_timings_without_publishing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    output = tmp_path / "capture.json"
    monkeypatch.setattr(sys, "argv", ["capture_scope.py", "--repo", str(repo), "--mode", "baseline", "--output", str(output), "--timings"])
    assert capture_scope.main() == 2
    result = capsys.readouterr()
    assert not result.out
    assert not output.exists()
    assert not output.with_suffix(".receipt.json").exists()
    timing = json.loads(result.err.splitlines()[-1])
    assert timing["exit_code"] == 2
    assert timing["phases"]["git.rev-parse"]["failed_calls"] == 1
    assert timing["phases"]["scope_capture"]["failed_calls"] == 1


def test_runtime_verification_failure_is_measured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import review_graph_session  # noqa: PLC0415 - patch the public CLI's deferred verification boundary.

    def changed() -> None:
        message = "frozen runtime resource changed"
        raise ValueError(message)

    monkeypatch.setattr(review_graph_session, "verify_current_snapshot", changed)
    monkeypatch.setattr(sys, "argv", ["capture_scope.py", "--timings"])
    with pytest.raises(ValueError, match="frozen runtime resource changed"):
        capture_scope.main()
    result = capsys.readouterr()
    assert not result.out
    timing = json.loads(result.err)
    assert timing["exit_code"] == 1
    assert timing["phases"]["runtime_verification"]["failed_calls"] == 1
    assert "scope_capture" not in timing["phases"]


@pytest.mark.parametrize(("mode", "extra", "code"), [("baseline", ("--help",), 0), ("invalid", (), 2)])
def test_parser_exit_timings_preserve_the_actual_cli_exit(tmp_path: Path, mode: str, extra: tuple[str, ...], code: int) -> None:
    result = _capture_result(tmp_path, mode, "--timings", *extra)
    assert result.returncode == code
    timing = json.loads(result.stderr.splitlines()[-1])
    assert timing["exit_code"] == code
    assert "scope_capture" not in timing["phases"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("mode", ["baseline", "staged"])
def test_batched_blob_bounds_preserve_binary_literal_paths_and_both_source_sides(tmp_path: Path, mode: str) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    # Cross the 64-object batch boundary; count exact bytes independently of Git.
    originals = {f"source-{index:03}\t[*]\n.bin": bytes([index]) + b"\0\r\n" * index + b"tail\xff" for index in range(70)}
    originals["empty.bin"] = b""
    for name, content in originals.items():
        (repo / name).write_bytes(content)
    _commit_all(repo)
    expected = {name: value.count(b"\n") + int(bool(value) and not value.endswith(b"\n")) for name, value in originals.items()}
    for name in originals:
        (repo / name).write_bytes(b"short\n")
    _git(repo, "add", ".")
    if mode == "staged":
        for name in originals:
            (repo / name).write_bytes(b"unstaged\n" * 100)
    capture = _capture(repo, mode)
    assert capture["captured_path_line_bounds"] == {name: max(1, bound) for name, bound in expected.items()}


def test_capture_still_reads_both_content_observations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    source = repo / "source.py"
    source.write_bytes(b"before\n")
    _commit_all(repo)
    original = capture_scope._captured_path_line_bounds

    def change_between_observations(**kwargs: Any) -> dict[str, int]:
        bounds = original(**kwargs)
        metadata = source.stat()
        # Preserve size and mtime: cached stat metadata cannot prove content.
        source.write_bytes(b"after!\n")
        os.utime(source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        return bounds

    monkeypatch.setattr(capture_scope, "_captured_path_line_bounds", change_between_observations)
    with pytest.raises(RuntimeError, match="captured source changed while deriving path line bounds"):
        capture_scope._scope_data(shutil.which("git") or "git", repo, "baseline", None, ())


@pytest.mark.parametrize("failure", ["missing", "wrong-object", "truncated", "trailing"])
def test_batch_blob_transport_rejects_incomplete_or_unbound_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    object_id = b"1" * 40
    output = object_id + b" blob 4\nraw\n\n"
    if failure == "missing":
        output = object_id + b" missing\n"
    elif failure == "wrong-object":
        output = output.replace(object_id, b"2" * 40)
    elif failure == "truncated":
        output = output[:-1]
    else:
        output += b"unbound\n"

    def query(_git: str, _repo: Path, arguments: Any, **_kwargs: Any) -> bytes:
        return object_id + b" blob 4\n" if "--batch-check" in arguments else output

    monkeypatch.setattr(capture_scope, "_run_git", query)
    with pytest.raises(RuntimeError, match="captured Git batch"):
        capture_scope._batch_blob_line_bounds("git", tmp_path, [object_id])


def test_blob_batches_bound_payload_bytes_and_keep_oversized_blobs_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    contents = [b"a\n" * 5, b"b" * 10, b"c\n" * 10, b"d" * 100, b"e\nz\n?"]
    for index, content in enumerate(contents):
        (repo / f"source-{index}.bin").write_bytes(content)
    _commit_all(repo)
    object_ids = [_git(repo, "rev-parse", f"HEAD:source-{index}.bin").strip().encode() for index in range(len(contents))]
    sizes = dict(zip(object_ids, map(len, contents), strict=True))
    batches = []
    run_git = capture_scope._run_git

    def query(git: str, root: Path, arguments: Any, *, payload: bytes | None = None) -> bytes:
        if "--batch" in arguments:
            assert payload is not None
            batches.append(payload.splitlines())
        return run_git(git, root, arguments, payload=payload)

    monkeypatch.setattr(capture_scope, "_BLOB_BATCH_BYTES", 32, raising=False)
    monkeypatch.setattr(capture_scope, "_run_git", query)
    bounds = capture_scope._batch_blob_line_bounds(shutil.which("git") or "git", repo, [*object_ids, object_ids[0]])
    assert bounds == dict(zip(object_ids, [5, 1, 10, 1, 3], strict=True))
    assert [oid for batch in batches for oid in batch] == object_ids
    assert any(len(batch) > 1 for batch in batches)
    assert [object_ids[3]] in batches
    assert all(len(batch) == 1 or sum(sizes[oid] for oid in batch) <= 32 for batch in batches)


@pytest.mark.parametrize("failure", ["missing", "truncated", "trailing"])
def test_blob_metadata_failure_stops_before_reading_payloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    object_id = b"1" * 40
    output = {"missing": object_id + b" missing\n", "truncated": b"", "trailing": object_id + b" blob 4\nextra\n"}[failure]

    def query(_git: str, _repo: Path, arguments: Any, **_kwargs: Any) -> bytes:
        assert "--batch-check" in arguments
        return output

    monkeypatch.setattr(capture_scope, "_run_git", query)
    with pytest.raises(RuntimeError, match="captured Git batch"):
        capture_scope._batch_blob_line_bounds("git", tmp_path, [object_id])


def test_repeated_426_path_capture_observes_content_index_mode_and_symlink_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    for index in range(426):
        (repo / f"source-{index:04}.rs").write_bytes(f"pub const VALUE: usize = {index};\n".encode())
    _commit_all(repo)
    git = shutil.which("git") or "git"

    def capture() -> dict[str, object]:
        index = (repo / ".git/index").read_bytes()
        entries = _git(repo, "ls-files", "--stage", "-z")
        with collect_timings() as timing:
            manifest = capture_scope._scope_data(git, repo, "baseline", None, ())
        # Guard subprocess scaling, not machine-dependent wall time. Both full
        # content observations and repository-state observation remain present.
        assert sum(value.calls for name, value in timing.phases.items() if name.startswith("git.")) < 40
        assert timing.phases["worktree_content_and_modes"].calls == 4
        assert (repo / ".git/index").read_bytes() == index
        assert _git(repo, "ls-files", "--stage", "-z") == entries
        return manifest

    original = capture()
    assert capture() == original
    source = repo / "source-0000.rs"
    metadata = source.stat()
    os.utime(source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns - 2_000_000_000))
    assert capture() == original
    metadata = source.stat()
    source.write_bytes(b"pub const VALUE: usize = 9;\n")
    os.utime(source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    content = capture()
    assert content["scope_fingerprint"] != original["scope_fingerprint"]
    _git(repo, "add", "--", source.name)
    staged = capture()
    assert staged["index_fingerprint"] != content["index_fingerprint"]
    assert staged["repository_path_fingerprints"] == content["repository_path_fingerprints"]
    source.chmod(0o755)
    executable = capture()
    assert executable["scope_fingerprint"] != staged["scope_fingerprint"]
    source.unlink()
    source.symlink_to("source-0001.rs")
    linked = capture()
    assert linked["scope_fingerprint"] != executable["scope_fingerprint"]
    assert linked["repository_symlink_paths"] == [source.name]


@pytest.mark.parametrize("failure", ["error", "timeout"])
def test_published_inspection_preserves_binary_errors_and_bounded_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    def result(args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["timeout"] == 30
        assert kwargs["input"] == b""
        assert args[-2:] == ["--", "literal\t[*]\n.bin"]
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 30, output=b"partial\r\n\xff\0", stderr=b"diagnostic\xff")
        return subprocess.CompletedProcess(args, 128, b"partial\r\n\xff\0", b"fatal\xff\n")

    monkeypatch.setattr(git_inspect, "run_git_bytes", result)
    with collect_timings() as timing, pytest.raises((subprocess.CalledProcessError, subprocess.TimeoutExpired)) as error:
        capture_scope._diff_paths(tmp_path, ("literal\t[*]\n.bin",), base="HEAD")
    assert error.value.stdout == b"partial\r\n\xff\0"
    assert error.value.stderr == (b"diagnostic\xff" if failure == "timeout" else b"fatal\xff\n")
    assert timing.phases["git.diff"].failed_calls == 1


def test_commit_verification_preserves_stale_index_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    source = repo / "source.py"
    source.write_bytes(b"original\n")
    _commit_all(repo)
    source.write_bytes(b"reviewed\n")
    before = _capture(repo, "baseline")
    _commit_all(repo)
    after = _capture(repo, "baseline")
    metadata = source.stat()
    os.utime(source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns - 2_000_000_000))
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "1")
    index = (repo / ".git/index").read_bytes()
    entries = _git(repo, "ls-files", "--stage", "-z")
    assert verify_live_commit(before, after) == before["head"]
    assert (repo / ".git/index").read_bytes() == index
    assert _git(repo, "ls-files", "--stage", "-z") == entries


@pytest.mark.parametrize("boundary", ["source-change", "plan"])
@pytest.mark.parametrize("failure", ["error", "timeout"])
def test_shared_capture_errors_retain_boundary_classification_and_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str, failure: str
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "source.py").write_bytes(b"source\n")
    _commit_all(repo)
    capture = _capture(repo, "baseline")
    error = (
        subprocess.CalledProcessError(128, ["git", "diff"], output=b"partial\r\n", stderr=b"fatal\xff")
        if failure == "error"
        else subprocess.TimeoutExpired(["git", "status"], 30, output=b"partial\r\n", stderr=b"fatal\xff")
    )

    def failed_capture(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise error

    owner = review_graph_source_change if boundary == "source-change" else review_graph_plan
    monkeypatch.setattr(owner, "_scope_data", failed_capture)
    operation = (
        partial(review_graph_source_change.verify_live_source, capture)
        if boundary == "source-change"
        else partial(review_graph_plan._verified_captured_source, capture, ("source.py",), repo, (("source.py", 1),))
    )
    message = "live source capture failed" if boundary == "source-change" else "could not independently verify captured source line bounds"
    with pytest.raises(ValueError, match=message) as observed:
        operation()
    assert observed.value.__cause__ is error
    if boundary == "source-change":
        assert isinstance(observed.value, EvaluationBoundaryError)
        assert observed.value.kind == RejectionKind.STALE_CAPTURE
    assert "partial" in str(observed.value)
    assert "fatal�" in str(observed.value)
