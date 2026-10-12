"""Declared caches stay bounded while source and ordinary output remain content-bound."""

import json
import os
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from review_graph_plan import ValidationArtifact, _verified_artifact_status
from review_graph_runtime import _validation_unit, _validation_workspace_audit, _workspace_content_digest, capture_workspace_snapshot
from test_review_graph_runtime import _baseline_mutation_fixture, _run_test_git

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager


def _cache_dispatch(tmp_path: Path, name: str, status: str) -> tuple[dict[str, Any], Path, Path]:
    git, repository, _template, _capture, plan = _baseline_mutation_fixture(tmp_path)
    (repository / ".gitignore").write_text(f"{name}/\n", encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "add", ".gitignore")
    isolation = tmp_path / "external"
    cache = repository / name if status == "ignored" else isolation / name
    cache.mkdir(parents=True)
    raw_path = name if status == "ignored" else str(cache)
    status_source, status_rule = _verified_artifact_status(raw_path, status, repository, str(isolation))
    artifact = ValidationArtifact(path=raw_path, kind="cache", repository_status=status, status_source=status_source, status_rule=status_rule)
    unit = replace(plan.coalesced_validation_units[0], allowed_artifacts=(artifact,), expected_workspace_effects=(raw_path,), isolation_root=str(isolation))
    return {"repository_root": str(repository), "validation_unit": json.loads(json.dumps(asdict(unit)))}, cache, repository


@pytest.mark.parametrize(("name", "status"), [(".uv-cache", "ignored"), (".research-repo-tools", "ignored"), ("application-wheel-store", "outside-repository")])
def test_declared_cache_roots_never_read_nested_directories_or_contents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, status: str) -> None:
    dispatch, cache, _repository = _cache_dispatch(tmp_path, name, status)
    nested = cache / "packages" / "unpacked" / "payload"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"cache payload must not be read")
    original_read_bytes, original_scandir = Path.read_bytes, os.scandir
    scanned: list[Path] = []

    def guarded_read_bytes(path: Path) -> bytes:
        if path.is_relative_to(cache):
            msg = "declared cache payload must not be read"
            raise AssertionError(msg)
        return original_read_bytes(path)

    def guarded_scandir(path: str | Path) -> AbstractContextManager[Iterator[os.DirEntry[str]]]:
        candidate = Path(path)
        if candidate.is_relative_to(cache):
            scanned.append(candidate)
            if candidate != cache:
                msg = "declared cache descendants must not be traversed"
                raise AssertionError(msg)
        return original_scandir(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(os, "scandir", guarded_scandir)
    snapshot = capture_workspace_snapshot(dispatch)

    assert scanned == [cache]
    assert snapshot["records"][0]["snapshot_mode"] == "bounded-directory-metadata-v3"
    assert snapshot["records"][0]["status"] == status
    assert snapshot["records"][0]["path"] == dispatch["validation_unit"]["allowed_artifacts"][0]["path"]


def test_declared_cache_binds_every_immediate_entry_outside_the_diagnostic_sample(tmp_path: Path) -> None:
    dispatch, cache, _repository = _cache_dispatch(tmp_path, "application-wheel-store", "outside-repository")
    for ordinal in range(300):
        (cache / f"artifact-{ordinal:03d}").write_text(str(ordinal), encoding="utf-8")
    fixed_timestamp_ns = 1_700_000_000_000_000_000
    os.utime(cache, ns=(fixed_timestamp_ns, fixed_timestamp_ns))
    before = capture_workspace_snapshot(dispatch)

    changed = cache / "artifact-299"
    changed.write_text("changed metadata beyond the first 256 entries", encoding="utf-8")
    os.utime(cache, ns=(fixed_timestamp_ns, fixed_timestamp_ns))
    after_metadata = capture_workspace_snapshot(dispatch)
    changed.rename(cache / "artifact-399")
    os.utime(cache, ns=(fixed_timestamp_ns, fixed_timestamp_ns))
    after_rename = capture_workspace_snapshot(dispatch)

    assert before["records"][0]["snapshot_mode"] == "bounded-directory-metadata-v3"
    assert before["records"][0]["digest"] != after_metadata["records"][0]["digest"]
    assert after_metadata["records"][0]["digest"] != after_rename["records"][0]["digest"]


def test_declared_cache_file_and_ordinary_report_directory_remain_content_hashed(tmp_path: Path) -> None:
    dispatch, cache, _repository = _cache_dispatch(tmp_path, "custom-cache", "outside-repository")
    cache.rmdir()
    cache.write_bytes(b"initial")
    before_file = capture_workspace_snapshot(dispatch)
    timestamp = cache.stat().st_mtime_ns
    cache.write_bytes(b"changed")
    os.utime(cache, ns=(timestamp, timestamp))
    after_file = capture_workspace_snapshot(dispatch)
    assert before_file["records"][0]["snapshot_mode"] == "content-sha256-v1"
    assert before_file["records"][0]["digest"] != after_file["records"][0]["digest"]

    cache.unlink()
    output = cache / "nested" / "report.json"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"initial")
    dispatch["validation_unit"]["allowed_artifacts"][0]["kind"] = "report"
    before_report = capture_workspace_snapshot(dispatch)
    timestamp = output.stat().st_mtime_ns
    output.write_bytes(b"changed")
    os.utime(output, ns=(timestamp, timestamp))
    after_report = capture_workspace_snapshot(dispatch)
    assert before_report["records"][0]["snapshot_mode"] == "recursive-content-sha256-v2"
    assert before_report["records"][0]["digest"] != after_report["records"][0]["digest"]


def test_cache_declaration_cannot_hide_tracked_source_tampering(tmp_path: Path) -> None:
    dispatch, cache, repository = _cache_dispatch(tmp_path, "source-cache", "ignored")
    source = cache / "nested" / "tracked.py"
    source.parent.mkdir()
    source.write_bytes(b"initial")
    # Use the fixture's tracked rule, while deliberately declaring a tracked tree as cache output.
    executable = shutil.which("git")
    assert executable is not None
    _run_test_git(executable, "-C", str(repository), "add", "-f", "source-cache/nested/tracked.py")
    before = capture_workspace_snapshot(dispatch)
    timestamps = {path: path.stat().st_mtime_ns for path in (source, source.parent, cache)}
    source.write_bytes(b"changed")
    for path, timestamp in timestamps.items():
        os.utime(path, ns=(timestamp, timestamp))
    after = capture_workspace_snapshot(dispatch)

    assert before["records"][0]["status"] == after["records"][0]["status"] == "tracked"
    assert before["records"][0]["snapshot_mode"] == "recursive-content-sha256-v2"
    assert before["records"][0]["digest"] != after["records"][0]["digest"]
    unit = _validation_unit(dispatch["validation_unit"])
    with pytest.raises(ValueError, match="tracked or nonignored repository paths"):
        _validation_workspace_audit({**dispatch, "workspace_before": before["records"], "workspace_after": after["records"]}, unit)


def test_declared_cache_policy_preserves_symlink_identity_without_following_contents(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    payload = target / "payload"
    payload.write_bytes(b"initial")
    link = tmp_path / "custom-cache"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Symlink creation unavailable: {error}")
    before = _workspace_content_digest(link, declared_cache=True)
    payload.write_bytes(b"changed")
    after_contents = _workspace_content_digest(link, declared_cache=True)
    link.unlink()
    link.symlink_to("different-target", target_is_directory=True)
    after_target = _workspace_content_digest(link, declared_cache=True)

    assert before == after_contents
    assert before[2] == after_target[2] == "symlink-target-v1"
    assert before[1] != after_target[1]
