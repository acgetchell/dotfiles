"""Keep untracked private files out of disposable build contexts."""

import shutil
import subprocess
from typing import TYPE_CHECKING

import docker_rebuild

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_snapshot_requires_staging_new_files_and_ignores_private_untracked_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = tmp_path / "checkout"
    repository.mkdir()
    public = repository / "public.txt"
    public.write_text("committed public source")
    git = shutil.which("git")
    assert git is not None
    for arguments in (
        ["init", "-q"],
        ["add", "public.txt"],
        ["-c", "commit.gpgSign=false", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
    ):
        subprocess.run([git, *arguments], cwd=repository, check=True, capture_output=True, timeout=10)  # noqa: S603 - disposable fixture only.
    public.write_text("current public source")
    private = repository / ".env"
    private.write_text("TOKEN=dummy-private-fixture")
    additional = repository / "new-source.txt"
    additional.write_text("explicitly selected public source")
    monkeypatch.setattr(docker_rebuild, "ROOT", repository)
    first = tmp_path / "first-context"
    before = docker_rebuild.snapshot(first)
    assert {path.name for path in first.iterdir()} == {"public.txt"}
    assert (first / "public.txt").read_text() == "current public source"
    private.write_text("TOKEN=changed-private-fixture")
    assert docker_rebuild.snapshot(tmp_path / "second-context") == before
    subprocess.run([git, "add", "new-source.txt"], cwd=repository, check=True, capture_output=True, timeout=10)  # noqa: S603 - explicit fixture opt-in.
    selected = tmp_path / "selected-context"
    after = docker_rebuild.snapshot(selected)
    assert {path.name for path in selected.iterdir()} == {"public.txt", "new-source.txt"}
    assert (selected / "new-source.txt").read_text() == additional.read_text()
    assert after["commit"] == before["commit"]
    assert after["content_digest"] != before["content_digest"]
