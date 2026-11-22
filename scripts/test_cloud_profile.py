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
import tomllib
from contextlib import suppress
from typing import TYPE_CHECKING

import pytest

import cloud_profile

if TYPE_CHECKING:
    from pathlib import Path


PROFILE_UV_PIN = tomllib.loads((cloud_profile.ROOT / "pyproject.toml").read_text())["tool"]["uv"]["required-version"].removeprefix("==")


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a disposable repository; never mutate the user's repository index."""
    root = tmp_path / "checkout with spaces"
    root.mkdir()
    pin = PROFILE_UV_PIN
    (root / "pyproject.toml").write_text(f'[project]\nname="fixture"\nversion="1.0.0"\n[tool.uv]\nrequired-version="=={pin}"\n')
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
        f"PIN = {pin!r}\n"
        "if sys.argv[1:] == ['--version']:\n print('uv', PIN); sys.exit(0)\n"
        "if sys.argv[1:3] == ['pip', 'install']:\n"
        " if os.environ.get('UV_OFFLINE') or os.environ.get('FORBID_INSTALL'): sys.exit(9)\n"
        " assert '--only-binary' in sys.argv and '--no-python-downloads' in sys.argv\n"
        " requested = sys.argv[-1].removeprefix('uv==')\n"
        " staged = Path(sys.argv[sys.argv.index('--target')+1]) / 'bin/uv'\n"
        " staged.parent.mkdir()\n"
        " staged.write_text(Path(__file__).read_text().replace(f'PIN = {PIN!r}', f'PIN = {requested!r}', 1))\n"
        " staged.chmod(0o700)\n"
        " sys.exit(0)\n"
        "with Path(os.environ['OBSERVATIONS']).open('a') as stream:\n"
        " stream.write(json.dumps({'argv':sys.argv[1:], 'offline':os.environ.get('UV_OFFLINE'), "
        "'downloads':os.environ.get('UV_PYTHON_DOWNLOADS'), 'environment':os.environ.get('UV_PROJECT_ENVIRONMENT'), "
        "'uv':PIN})+'\\n')\n"
        "if os.environ.get('MUTATE_SOURCE'):\n Path('pyproject.toml').write_text('changed')\n"
        "if os.environ.get('FAIL_COMMAND'):\n print('offline cache unavailable private-marker',file=sys.stderr); sys.exit(7)\n"
        "if os.environ.get('CHILD_PID'):\n Path(os.environ['CHILD_PID']).write_text(str(os.getpid())); time.sleep(60)\n"
    )
    uv.chmod(0o700)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("OBSERVATIONS", str(tmp_path / "observations.jsonl"))
    return root


@pytest.fixture
def mixed_inventory(checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    """Two separate checkouts with different owning pins and recipe selections."""
    second = tmp_path / "another checkout"
    git = shutil.which("git")
    assert git is not None
    # Clone the committed tree so Git's transient maintenance files stay in the source.
    subprocess.run([git, "clone", "--no-local", "--quiet", "--", checkout, second], check=True, capture_output=True, timeout=10)  # noqa: S603 - fixture paths.
    metadata = second / "pyproject.toml"
    metadata.write_text(metadata.read_text().replace(f"=={PROFILE_UV_PIN}", "==0.13.7"))
    inventory = tmp_path / "inventory.toml"
    inventory.write_text(
        f'schema_version=1\n[[repository]]\nname="first"\npath={json.dumps(str(checkout))}\n'
        f'[[repository]]\nname="second"\npath={json.dumps(str(second))}\ngroups=["tools", "build"]\n'
        'tools=[["setup-tools", "check-tools"]]\n'
    )
    just = tmp_path / "bin/just"
    just.write_text('#!/bin/sh\nexec uv "$@"\n')
    just.chmod(0o700)
    prefix = tmp_path / "persistent tools"
    monkeypatch.setenv("DOTFILES_REVIEW_PREFIX", str(prefix))
    return inventory, second, prefix / "uv/0.13.7/uv"


def test_mixed_uv_pins_provision_and_restore_offline(
    checkout: Path, tmp_path: Path, mixed_inventory: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory, second, retained = mixed_inventory
    observations = tmp_path / "observations.jsonl"
    uv_paths = [str(tmp_path / "bin/uv"), str(retained)]
    pins = [PROFILE_UV_PIN, "0.13.7"]
    original_sources = [cloud_profile.source_identity(path) for path in (checkout, second)]
    original_locks = [(path / "uv.lock").read_bytes() for path in (checkout, second)]
    for index, mode in enumerate(("provision", "provision", "startup", "startup", "doctor")):
        if index:
            monkeypatch.setenv("FORBID_INSTALL", "1")
            observations.unlink()
        receipts = tmp_path / f"receipts-{index}"
        assert cloud_profile.main([mode, "--inventory", str(inventory), "--receipts", str(receipts)]) == 0
        receipt = json.loads(next(receipts.glob("*/receipt.json")).read_text())
        reports = receipt["repositories"]
        assert [entry["uv_executable"] for entry in reports] == uv_paths
        assert [entry["uv_required_version"] for entry in reports] == pins
        assert [entry["uv"] for entry in reports] == [f"uv {pin}" for pin in pins]
        installs = [command["argv"] for report in reports for command in report["commands"] if command["argv"][1:3] == ["pip", "install"]]
        assert [command[-1] for command in installs] == (["uv==0.13.7"] if index == 0 else [])
        assert [entry["source_before"] for entry in reports] == [entry["source_after"] for entry in reports] == original_sources
        assert [entry["lock_sha256"] for entry in reports] == [hashlib.sha256(lock).hexdigest() for lock in original_locks]
        commands = [json.loads(line) for line in observations.read_text().splitlines()]
        first = [entry for entry in commands if entry["environment"] == str(checkout / ".venv")]
        alternate = [entry for entry in commands if entry["environment"] == str(second / ".venv")]
        assert len(commands) == len(first) + len(alternate)
        assert {entry["uv"] for entry in first} == {pins[0]}
        assert {entry["uv"] for entry in alternate} == {pins[1]}
        assert first[0]["argv"][:4] == ["sync", "--locked", "--group", "dev"]
        assert alternate[0]["argv"][:6] == ["sync", "--locked", "--group", "tools", "--group", "build"]
        assert [entry["argv"] for entry in alternate if entry["argv"][0] != "sync"] == (
            [["setup-tools"], ["check-tools"]] if mode == "provision" else [["check-tools"]]
        )
        if mode != "provision":
            assert all(entry["offline"] == "1" and entry["downloads"] == "never" for entry in commands)
        if mode == "doctor":
            assert [entry["argv"][-1] for entry in commands if entry["argv"][0] == "sync"] == ["--check", "--check"]
    assert [(path / "uv.lock").read_bytes() for path in (checkout, second)] == original_locks


@pytest.mark.parametrize("mode", ["startup", "doctor"])
@pytest.mark.parametrize("retained_state", ["missing", "wrong-version", "non-executable"])
def test_offline_modes_fail_closed_for_invalid_retained_uv(
    tmp_path: Path, mixed_inventory: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch, mode: str, retained_state: str
) -> None:
    inventory, second, retained = mixed_inventory
    bootstrap = tmp_path / "bin/uv"
    # A different PATH entry may even match the second pin. Offline runs still require the retained executable.
    alternate = tmp_path / "alternate"
    alternate.mkdir()
    candidate = alternate / "uv"
    candidate.write_text(bootstrap.read_text().replace(f"PIN = {PROFILE_UV_PIN!r}", "PIN = '0.13.7'", 1))
    candidate.chmod(0o700)
    monkeypatch.setenv("PATH", f"{os.environ['PATH']}{os.pathsep}{alternate}")
    if retained_state != "missing":
        retained.parent.mkdir(parents=True)
        retained.write_bytes(bootstrap.read_bytes())
        if retained_state == "wrong-version":
            retained.chmod(0o700)
    monkeypatch.setenv("FORBID_INSTALL", "1")
    receipts = tmp_path / "receipts"
    assert cloud_profile.main([mode, "--inventory", str(inventory), "--receipts", str(receipts)]) == 2
    receipt = json.loads(next(receipts.glob("*/receipt.json")).read_text())
    assert receipt["repositories"][1]["commands"] == []
    diagnostic = receipt["diagnostic"]
    assert diagnostic.startswith("second: retained uv")
    assert "0.13.7" in diagnostic
    assert "connected cloud-provision" in diagnostic
    assert not (second / ".venv").exists()


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
    # Isolate platform selection so every review host exercises Python isolation.
    uname = binaries / "uname"
    uname.write_text('#!/bin/sh\ncase "$1" in -s) echo Darwin ;; -m) echo x86_64 ;; *) exit 2 ;; esac\n')
    uname.chmod(0o700)
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


def test_receipt_destination_error_has_a_private_cli_diagnostic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    destination = tmp_path / "private-filename"
    destination.write_text("preserve", encoding="utf-8")
    assert cloud_profile.main(["doctor", "--receipts", str(destination)]) == 2
    captured = capsys.readouterr()
    assert "receipt" in captured.err
    assert "private-filename" not in captured.err
    assert not captured.out
    assert destination.read_text(encoding="utf-8") == "preserve"


def test_unwritable_final_receipt_prevents_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def no_repositories(_inventory: Path) -> tuple[tuple[()], str]:
        attempt = next(tmp_path.glob("doctor-*"))
        (attempt / "receipt.json").mkdir()
        return (), "fixture"

    monkeypatch.setattr(cloud_profile, "load_inventory", no_repositories)
    previous = signal.getsignal(signal.SIGTERM)
    assert cloud_profile.main(["doctor", "--receipts", str(tmp_path)]) == 2
    assert signal.getsignal(signal.SIGTERM) == previous
    captured = capsys.readouterr()
    assert "cannot write lifecycle receipt" in captured.err
    assert not captured.out


def test_receipt_hashes_the_inventory_bytes_actually_parsed(checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inventory = tmp_path / "inventory.toml"
    original = f'schema_version=1\n[[repository]]\nname="fixture"\npath={json.dumps(str(checkout))}\n'.encode()
    inventory.write_bytes(original)
    read_bytes = type(inventory).read_bytes
    reads = []

    def observed_read(path: Path) -> bytes:
        """Track reads of the inventory while leaving other file access untouched."""
        content = read_bytes(path)
        if path == inventory:
            reads.append(path)
        return content

    parse_repository = cloud_profile.parse_repository

    def replace_after_parse(raw: object, directory: Path) -> cloud_profile.RepositoryProfile:
        """Rewrite the inventory after parsing so a second read would hash different bytes."""
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
