"""Exercise lifecycle boundaries with isolated repositories and command stand-ins."""

import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from contextlib import suppress
from typing import TYPE_CHECKING

import pytest

import cloud_profile

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a disposable repository; never mutate the user's repository index."""
    root = tmp_path / "checkout with spaces"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="1.0.0"\n[tool.uv]\nrequired-version="==0.13.8"\n')
    (root / "uv.lock").write_text('version=1\n[[package]]\nname="fixture"\nversion="1.0.0"\n[package.source]\neditable="."\n')
    (root / ".gitignore").write_text(".venv/\n")
    git = shutil.which("git")
    assert git is not None
    for arguments in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "commit.gpgSign=false", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
    ):
        subprocess.run([git, *arguments], cwd=root, check=True, capture_output=True, timeout=10)  # noqa: S603 - disposable fixture only.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    uv = binaries / "uv"
    uv.write_text(
        f"#!{sys.executable}\nimport json, os, sys, time\nfrom pathlib import Path\n"
        "if sys.argv[1:] == ['--version']:\n print('uv 0.13.8'); sys.exit(0)\n"
        "with Path(os.environ['OBSERVATIONS']).open('a') as stream:\n"
        " stream.write(json.dumps({'argv':sys.argv[1:], 'offline':os.environ.get('UV_OFFLINE'), "
        "'downloads':os.environ.get('UV_PYTHON_DOWNLOADS'), 'environment':os.environ.get('UV_PROJECT_ENVIRONMENT')})+'\\n')\n"
        "if os.environ.get('MUTATE_SOURCE'):\n Path('pyproject.toml').write_text('changed')\n"
        "if os.environ.get('FAIL_COMMAND'):\n print('offline cache unavailable private-marker',file=sys.stderr); sys.exit(7)\n"
        "if os.environ.get('CHILD_PID'):\n Path(os.environ['CHILD_PID']).write_text(str(os.getpid())); time.sleep(60)\n"
    )
    uv.chmod(0o700)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("OBSERVATIONS", str(tmp_path / "observations.jsonl"))
    return root


@pytest.mark.parametrize("mode", ["provision", "startup", "doctor"])
def test_lifecycle_preserves_source_and_uses_owned_environment(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: cloud_profile.Mode
) -> None:
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/unrelated/environment")
    profile = cloud_profile.RepositoryProfile("fixture", checkout)
    report: dict[str, object] = {}
    cloud_profile.run_repository(profile, mode, report)
    assert report["status"] == "passed"
    assert report["source_before"] == report["source_after"]
    commands = [json.loads(line) for line in (tmp_path / "observations.jsonl").read_text().splitlines()]
    assert commands[0]["environment"] == str(checkout / ".venv")
    assert "--locked" in commands[0]["argv"]
    if mode == "provision":
        assert commands[0]["offline"] is None
    else:
        assert all(command["offline"] == "1" and command["downloads"] == "never" for command in commands)
    if mode == "startup":
        assert commands[0]["argv"][-2:] == ["--reinstall-package", "fixture"]
        assert len(commands) == 3
        assert "--reinstall-package" not in commands[1]["argv"]
        assert "--check" not in commands[1]["argv"]
        assert commands[2]["argv"][-1] == "--check"
    if mode == "doctor":
        assert len(commands) == 1
        assert commands[0]["argv"][-1] == "--check"


def test_failed_offline_attempt_retains_safe_receipt_and_can_retry(checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inventory = tmp_path / "inventory.toml"
    inventory.write_text(f'schema_version=1\n[[repository]]\nname="fixture"\npath={json.dumps(str(checkout))}\n')
    receipts = tmp_path / "receipts"
    monkeypatch.setenv("FAIL_COMMAND", "1")
    arguments = ["startup", "--inventory", str(inventory), "--receipts", str(receipts)]
    assert cloud_profile.main(arguments) == 2
    failed = next(receipts.glob("*/receipt.json")).read_text()
    report = json.loads(failed)
    assert report["status"] == "failed"
    assert "cache" in report["diagnostic"]
    assert report["repositories"][0]["commands"][0]["exit_code"] == 7
    assert "private-marker" not in failed
    monkeypatch.delenv("FAIL_COMMAND")
    assert cloud_profile.main(arguments) == 0
    assert sorted(json.loads(path.read_text())["status"] for path in receipts.glob("*/receipt.json")) == ["failed", "passed"]


def test_source_mutation_is_reported_and_never_rolled_back(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUTATE_SOURCE", "1")
    with pytest.raises(ValueError, match="source or HEAD changed"):
        cloud_profile.run_repository(cloud_profile.RepositoryProfile("fixture", checkout), "startup", {})
    assert (checkout / "pyproject.toml").read_text() == "changed"


@pytest.mark.parametrize(
    "fields", [{"name": "bad name"}, {"groups": [False]}, {"tools": [["update", "check", "extra"]]}, {"review-environment": "yes"}, {"unknown": 1}]
)
def test_invalid_inventory_is_rejected_before_commands(checkout: Path, tmp_path: Path, fields: dict[str, object]) -> None:
    raw = {"name": "fixture", "path": str(checkout), **fields}
    with pytest.raises((ValueError, TypeError)):
        cloud_profile.parse_repository(raw, tmp_path)
    assert not (tmp_path / "observations.jsonl").exists()


def test_environment_lock_prevents_concurrent_mutation_and_releases_after_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    environment = tmp_path / "environment"
    with cloud_profile.environment_lock(environment), pytest.raises(ValueError, match="in use"), cloud_profile.environment_lock(environment):
        pytest.fail("second owner acquired the lock")
    with cloud_profile.environment_lock(environment):
        assert environment.exists() is False


def test_interruption_preserves_source_and_releases_environment_lock(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cloud_profile, "execute", interrupt)
    profile = cloud_profile.RepositoryProfile("fixture", checkout)
    report: dict[str, object] = {}
    with pytest.raises(KeyboardInterrupt):
        cloud_profile.run_repository(profile, "startup", report)
    assert report["source_before"] == report["source_after"]
    with cloud_profile.environment_lock(profile.environment):
        assert "status" not in report


@pytest.mark.parametrize("metadata", ['tool="bad"', '[tool]\nuv="bad"', "[tool.uv]\nrequired-version=12"])
def test_invalid_uv_pin_is_a_boundary_error(checkout: Path, tmp_path: Path, metadata: str) -> None:
    (checkout / "pyproject.toml").write_text(metadata)
    with pytest.raises(ValueError, match=r"exact.*required-version"):
        cloud_profile.run_repository(cloud_profile.RepositoryProfile("fixture", checkout), "startup", {})
    assert not (tmp_path / "observations.jsonl").exists()


def test_cloud_launcher_ignores_ambient_python_home(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    uv = binaries / "uv"
    uv.write_text(f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(sys.executable)}\n")
    uv.chmod(0o700)
    bash = shutil.which("bash")
    assert bash is not None
    result = subprocess.run(  # noqa: S603 - real repository launcher with an isolated tool-discovery fixture.
        [bash, str(cloud_profile.ROOT / "bin/cloud-profile.sh"), "--help"],
        env={**os.environ, "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}", "PYTHONHOME": str(tmp_path / "missing-python")},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "provision,startup,doctor" in result.stdout


def test_receipt_hashes_the_inventory_bytes_actually_parsed(checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inventory = tmp_path / "inventory.toml"
    original = f'schema_version=1\n[[repository]]\nname="fixture"\npath={json.dumps(str(checkout))}\n'.encode()
    inventory.write_bytes(original)
    read_bytes = type(inventory).read_bytes
    reads = []

    def observed_read(path: Path) -> bytes:
        content = read_bytes(path)
        if path == inventory:
            reads.append(path)
        return content

    parse_repository = cloud_profile.parse_repository

    def replace_after_parse(raw: object, directory: Path) -> cloud_profile.RepositoryProfile:
        profile = parse_repository(raw, directory)
        inventory.write_bytes(original.replace(b'name="fixture"', b'name="changed"'))
        return profile

    monkeypatch.setattr(type(inventory), "read_bytes", observed_read)
    monkeypatch.setattr(cloud_profile, "parse_repository", replace_after_parse)
    receipts = tmp_path / "receipts"
    assert cloud_profile.main(["doctor", "--inventory", str(inventory), "--receipts", str(receipts)]) == 0
    report = json.loads(next(receipts.glob("*/receipt.json")).read_text())
    assert reads == [inventory]
    assert report["inventory_sha256"] == hashlib.sha256(original).hexdigest()
    assert report["repositories"][0]["name"] == "fixture"


def stop_fixture_child(pid: int | None) -> None:
    """Clean up even when a termination regression leaves the fixture child running."""
    if os.name == "posix" and pid is not None:
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def test_sigterm_stops_child_before_retry_and_writes_failure_receipt(checkout: Path, tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.toml"
    inventory.write_text(f'schema_version=1\n[[repository]]\nname="fixture"\npath={json.dumps(str(checkout))}\n')
    receipts, pid_file = tmp_path / "receipts", tmp_path / "child.pid"
    child_pid = None
    process = subprocess.Popen(  # noqa: S603 - disposable lifecycle subprocess and blocking fixture tool.
        [sys.executable, str(cloud_profile.ROOT / "scripts/cloud_profile.py"), "startup", "--inventory", str(inventory), "--receipts", str(receipts)],
        env={**os.environ, "CHILD_PID": str(pid_file)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if pid_file.exists() and (text := pid_file.read_text()):
                child_pid = int(text)
                break
            time.sleep(0.01)
        assert child_pid is not None, "lifecycle did not start its child"
        process.terminate()
        process.communicate(timeout=10)
        assert process.returncode == 128 + signal.SIGTERM
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
        report = json.loads(next(receipts.glob("*/receipt.json")).read_text())
        assert report["status"] == "failed"
        assert "interrupted" in report["diagnostic"]
        assert report["repositories"][0]["commands"][0]["interrupted"] is True
        retry: dict[str, object] = {}
        cloud_profile.run_repository(cloud_profile.RepositoryProfile("fixture", checkout), "startup", retry)
        assert retry["status"] == "passed"
    finally:
        stop_fixture_child(child_pid)
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
