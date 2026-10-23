"""Exercise user-space provisioning boundaries without claiming native Linux evidence."""

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

import linux_review

REPOSITORY = Path(__file__).resolve().parents[1]


def executable(path: Path, body: str) -> None:
    """Create an isolated shell tool stand-in."""
    path.write_text(f"#!/bin/bash\nset -euo pipefail\n{body}\n")
    path.chmod(0o700)


def release_fixture(directory: Path, asset: str, member: str, body: str, sums: str) -> None:
    """Create real tar/zip bytes and their published checksum stand-ins."""
    content = f"#!/bin/bash\nset -euo pipefail\n{body}\n".encode()
    path = directory / asset
    if asset.endswith(".zip"):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(member, content)
    else:
        with tarfile.open(path, "w:gz") as archive:
            info = tarfile.TarInfo(member)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    (directory / sums).write_text(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {asset}\n")


def pin(pattern: str, path: Path) -> str:
    """Read a repository pin for the isolated release fixture."""
    match = re.search(pattern, path.read_text(), re.MULTILINE)
    assert match is not None
    value = match.group(1)
    assert isinstance(value, str)
    return value


@pytest.fixture
def linux_boundary(tmp_path: Path) -> dict[str, str]:
    """Provide fake host identity and transport with real archive bytes and computed checksums."""
    binaries = tmp_path / "base"
    releases = tmp_path / "releases"
    binaries.mkdir()
    releases.mkdir()
    # GNU tar invokes gzip through PATH when reading compressed release archives.
    for name in ("git", "bash", "env", "tar", "gzip", "unzip", "sed", "head", "awk", "mkdir", "mktemp", "chmod", "cp", "mv", "rm", "dirname"):
        tool = shutil.which(name)
        assert tool is not None
        (binaries / name).symlink_to(tool)
    # macOS need not install GNU coreutils to exercise the Linux boundary fixture.
    checksum = binaries / "sha256sum"
    checksum.write_text(
        f"#!{sys.executable}\nimport hashlib, sys\nfrom pathlib import Path\nprint(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest(), sys.argv[1])\n"
    )
    checksum.chmod(0o700)
    executable(binaries / "uname", 'case "$1" in -s) echo Linux ;; -m) echo x86_64 ;; esac')
    executable(binaries / "getconf", 'echo "${FAKE_LIBC:-glibc 2.39}"')
    for name in ("zsh", "stow", "cargo"):
        executable(binaries / name, f"echo {name} fixture")
    executable(binaries / "rustc", "echo 'rustc 1.85.0 (fixture)'")
    scanner_bin = tmp_path / "install/semgrep-venv/bin"
    scanner_bin.mkdir(parents=True)
    scanner_project = tomllib.loads((REPOSITORY / "tooling/semgrep/pyproject.toml").read_text())["project"]
    scanner_version = next(dependency.removeprefix("semgrep==") for dependency in scanner_project["dependencies"] if dependency.startswith("semgrep=="))
    scanner_observation = {"python_executable": str(scanner_bin / "python"), "python_version": "3.14.9", "semgrep_version": scanner_version}
    executable(scanner_bin / "python", f"printf '%s\\n' {shlex.quote(json.dumps(scanner_observation))}")
    executable(scanner_bin / "semgrep", f"echo semgrep {scanner_version}")
    executable(
        binaries / "curl",
        '[[ "${BLOCK_NETWORK:-0}" != 1 ]] || exit 7\n'
        'url="${@: -3:1}"\noutput="${@: -1}"\nasset="${url##*/}"\n'
        'printf "%s\\n" "$asset" >> "$DOWNLOAD_LOG"\ncp "$RELEASES/$asset" "$output"',
    )
    pins = {name: pin(rf'^{name}_version := "([^"]+)"', REPOSITORY / "justfile") for name in ("just", "dprint", "rumdl")}
    pins["uv"] = pin(r'^required-version = "==([^"]+)"', REPOSITORY / "pyproject.toml")
    uv_asset = "uv-x86_64-unknown-linux-gnu.tar.gz"
    release_fixture(
        releases,
        uv_asset,
        "uv-x86_64-unknown-linux-gnu/uv",
        f'if [[ "$1" == --version ]]; then echo uv {pins["uv"]}; else\n'
        'printf "%s\\n" "$*" >> "$CALL_LOG"\n'
        'printf "%s|%s\\n" "${UV_PYTHON-UNSET}" "$*" >> "$PYTHON_LOG"\n'
        'if [[ "$1" == sync && "$*" == *"--project tooling/semgrep"* ]]; then\n'
        '[[ "$UV_PROJECT_ENVIRONMENT" == "$DOTFILES_REVIEW_PREFIX/semgrep-venv" ]] || exit 29\nfi\n'
        'if [[ "$1" == run ]]; then\nshift\nwhile [[ "$1" == --* ]]; do shift; done\n'
        'export PATH="$UV_PROJECT_ENVIRONMENT/bin:$PATH"\n'
        '[[ "$1" == python && "$2" == scripts/linux_review.py ]]\nshift\n'
        f'exec {shlex.quote(sys.executable)} "$@"\nfi\nfi',
        uv_asset + ".sha256",
    )
    just_body = f'if [[ "$1" == --version ]]; then echo just {pins["just"]}; elif [[ "$1" == --evaluate ]]; then\ncase "$2" in\n'
    just_body += "\n".join(f"{name}_version) echo {value} ;;" for name, value in pins.items())
    just_body += (
        '\nesac\nelse\n[[ "$JUST_TEMPDIR" == "$DOTFILES_REVIEW_PREFIX/"* && -d "$JUST_TEMPDIR" ]]\n'
        'printf "%s\\n" "$*" >> "$CALL_LOG"; exit "${PLUGIN_CHECK_EXIT_CODE:-0}"; fi'
    )
    release_fixture(releases, f"just-{pins['just']}-x86_64-unknown-linux-musl.tar.gz", "just", just_body, "SHA256SUMS")
    release_fixture(releases, "dprint-x86_64-unknown-linux-gnu.zip", "dprint", f"echo dprint {pins['dprint']}", "SHASUMS256.txt")
    rumdl_asset = f"rumdl-v{pins['rumdl']}-x86_64-unknown-linux-gnu.tar.gz"
    release_fixture(releases, rumdl_asset, "rumdl", f"echo rumdl {pins['rumdl']}", rumdl_asset + ".sha256")
    return {
        **os.environ,
        "PATH": str(binaries),
        "DOTFILES_REVIEW_PREFIX": str(tmp_path / "install"),
        "DOTFILES_REVIEW_CACHE": str(tmp_path / "cache"),
        "DOTFILES_REVIEW_TMP": str(tmp_path / "tmp"),
        "DOTFILES_REVIEW_ARTIFACTS": str(tmp_path / "artifacts"),
        "DOTFILES_REVIEW_SKILLS_DIR": str(tmp_path / "skills"),
        "RELEASES": str(releases),
        "DOWNLOAD_LOG": str(tmp_path / "downloads"),
        "CALL_LOG": str(tmp_path / "calls"),
        "PYTHON_LOG": str(tmp_path / "python-selectors"),
    }


def run_installer(environment: dict[str, str], mode: str = "setup") -> subprocess.CompletedProcess[str]:
    """Run the real installer against the isolated host boundary."""
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(REPOSITORY / "bin/linux-review.sh"), mode], env=environment, capture_output=True, text=True, check=False, timeout=30
    )


def test_fresh_setup_and_rerun_use_pins_custom_storage_and_no_shell_changes(linux_boundary: dict[str, str]) -> None:
    for _ in range(2):
        result = run_installer(linux_boundary)
        assert result.returncode == 0, result.stderr
    assert len(Path(linux_boundary["DOWNLOAD_LOG"]).read_text().splitlines()) == 8
    assert {path.name for path in (Path(linux_boundary["DOTFILES_REVIEW_PREFIX"]) / "bin").iterdir()} == {"uv", "just", "dprint", "rumdl"}
    calls = Path(linux_boundary["CALL_LOG"]).read_text()
    assert calls.count("sync --locked --group dev") == 2
    assert calls.count("sync --locked --project tooling/semgrep") == 2
    assert "run --locked --no-sync python scripts/linux_review.py setup" in calls
    assert "yaml-fmt-check" in calls
    reports = list(Path(linux_boundary["DOTFILES_REVIEW_ARTIFACTS"]).glob("setup-*/environment.json"))
    assert len(reports) == 2
    assert all(json.loads(path.read_text())["status"] == "passed" for path in reports)


def test_uv_environment_does_not_shadow_provisioned_tools(linux_boundary: dict[str, str]) -> None:
    prefix = Path(linux_boundary["DOTFILES_REVIEW_PREFIX"])
    venv_bin = prefix / "venv/bin"
    venv_bin.mkdir(parents=True)
    executable(venv_bin / "just", "echo just 0.0.0")
    for mode in ("setup", "check"):
        result = run_installer(linux_boundary, mode)
        assert result.returncode == 0, result.stderr
        report_path = next(Path(linux_boundary["DOTFILES_REVIEW_ARTIFACTS"]).glob(f"{mode}-*/environment.json"))
        report = json.loads(report_path.read_text())
        assert report["status"] == "passed"
        assert report["tools"]["just"]["executable"] == str(prefix / "bin/just")
    assert "ci" in Path(linux_boundary["CALL_LOG"]).read_text().splitlines()


def test_root_python_selector_does_not_reach_scanner_setup_or_check(linux_boundary: dict[str, str]) -> None:
    """Site Python selection belongs to root tooling, not the older scanner project."""
    root_python = "/site modules/python 3.15/bin/python"
    linux_boundary["UV_PYTHON"] = root_python
    for mode in ("setup", "check"):
        result = run_installer(linux_boundary, mode)
        assert result.returncode == 0, result.stderr
    observations = [line.split("|", 1) for line in Path(linux_boundary["PYTHON_LOG"]).read_text().splitlines()]
    scanner_calls = [(selector, command) for selector, command in observations if "--project tooling/semgrep" in command]
    root_calls = [(selector, command) for selector, command in observations if "--project tooling/semgrep" not in command]
    assert len(scanner_calls) == 2
    assert any("--check" in command for _, command in scanner_calls)
    assert all(selector == "UNSET" for selector, _ in scanner_calls)
    assert root_calls
    assert all(selector == root_python for selector, _ in root_calls)


@pytest.mark.parametrize("tool", ["rustc", "cargo"])
@pytest.mark.parametrize("mode", ["setup", "check"])
def test_missing_rust_tool_fails_before_provisioning_or_checks(linux_boundary: dict[str, str], tool: str, mode: str) -> None:
    """A complete setup must detect the native Rust fixture's prerequisites."""
    if mode == "check":
        setup = run_installer(linux_boundary)
        assert setup.returncode == 0, setup.stderr
    logs = [Path(linux_boundary[name]) for name in ("DOWNLOAD_LOG", "CALL_LOG")]
    before = {path: path.read_bytes() if path.exists() else None for path in logs}
    (Path(linux_boundary["PATH"]) / tool).unlink()
    result = run_installer(linux_boundary, mode)
    assert result.returncode == 2
    assert f"Required tool '{tool}' unavailable" in result.stderr
    assert "setup complete" not in result.stdout
    assert {path: path.read_bytes() if path.exists() else None for path in logs} == before


@pytest.mark.parametrize("tool", ["rustc", "cargo"])
def test_direct_check_records_missing_rust_tool_without_launching_ci(linux_boundary: dict[str, str], tool: str) -> None:
    setup = run_installer(linux_boundary)
    assert setup.returncode == 0, setup.stderr
    linux_boundary["JUST_TEMPDIR"] = str(Path(linux_boundary["DOTFILES_REVIEW_PREFIX"]) / "recipe-tmp")
    linux_boundary["DOTFILES_SEMGREP_ENVIRONMENT"] = str(Path(linux_boundary["DOTFILES_REVIEW_PREFIX"]) / "semgrep-venv")
    (Path(linux_boundary["PATH"]) / tool).unlink()
    calls = Path(linux_boundary["CALL_LOG"])
    before = calls.read_bytes()
    result = subprocess.run(  # noqa: S603 - real launcher with isolated host tools and artifact storage.
        [sys.executable, str(REPOSITORY / "scripts/linux_review.py"), "check"], env=linux_boundary, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 2
    report_path = next(Path(linux_boundary["DOTFILES_REVIEW_ARTIFACTS"]).glob("check-*/environment.json"))
    report = json.loads(report_path.read_text())
    assert report["status"] == "unavailable"
    assert tool in report["diagnostic"]
    assert not (report_path.parent / "launch.json").exists()
    assert calls.read_bytes() == before


@pytest.mark.parametrize("mode", ["setup", "check", "direct-check"])
@pytest.mark.parametrize(
    ("identity", "compiler_exit", "supported"),
    [
        ("rustc 1.84.1 (old fixture)", 0, False),
        ("rustc 1.85.0 (fixture)", 0, True),
        ("rustc 1.85.0-beta.1 (fixture)", 0, True),
        ("rustc 1.85.0-nightly (fixture)", 0, True),
        ("rustc 1.84.0-nightly (old fixture)", 0, False),
        ("rustc 2.0.0 (fixture)", 0, True),
        ("rustc unknown", 0, False),
        ("rustc 1.85.0oops", 0, False),
        pytest.param("rustc 1.85.0 (fixture)", 7, False, id="failed_probe"),
    ],
)
def test_rust_version_floor_is_checked_before_work(linux_boundary: dict[str, str], mode: str, identity: str, compiler_exit: int, *, supported: bool) -> None:
    """Reject old/malformed compilers before downloads or the expensive suite."""
    if mode != "setup":
        setup = run_installer(linux_boundary)
        assert setup.returncode == 0, setup.stderr
    executable(Path(linux_boundary["PATH"]) / "rustc", f"echo {shlex.quote(identity)}\nexit {compiler_exit}")
    logs = [Path(linux_boundary[name]) for name in ("DOWNLOAD_LOG", "CALL_LOG")]
    before = {path: path.read_bytes() if path.exists() else None for path in logs}
    linux_boundary["JUST_TEMPDIR"] = str(Path(linux_boundary["DOTFILES_REVIEW_PREFIX"]) / "recipe-tmp")
    linux_boundary["DOTFILES_SEMGREP_ENVIRONMENT"] = str(Path(linux_boundary["DOTFILES_REVIEW_PREFIX"]) / "semgrep-venv")
    argv = (
        [sys.executable, str(REPOSITORY / "scripts/linux_review.py"), "check"]
        if mode == "direct-check"
        else ["/bin/bash", str(REPOSITORY / "bin/linux-review.sh"), mode]
    )
    result = subprocess.run(argv, env=linux_boundary, capture_output=True, text=True, check=False, timeout=30)  # noqa: S603 - isolated host boundary.
    assert result.returncode == (0 if supported else 2), result.stderr
    if not supported:
        diagnostic = "rustc" if compiler_exit and mode == "direct-check" else "Rust >= 1.85"
        assert diagnostic in result.stderr
        assert {path: path.read_bytes() if path.exists() else None for path in logs} == before
        if mode == "direct-check":
            report_path = next(Path(linux_boundary["DOTFILES_REVIEW_ARTIFACTS"]).glob("check-*/environment.json"))
            assert json.loads(report_path.read_text())["status"] == "unavailable"
            assert not (report_path.parent / "launch.json").exists()


@pytest.mark.parametrize("existing_path", [None, ""])
def test_missing_path_does_not_add_current_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing_path: str | None) -> None:
    monkeypatch.chdir(tmp_path)
    executable(tmp_path / "untrusted-tool", "exit 0")
    prefix = tmp_path / "install"
    monkeypatch.setenv("DOTFILES_REVIEW_PREFIX", str(prefix))
    monkeypatch.setenv("DOTFILES_REVIEW_ARTIFACTS", str(tmp_path / "artifacts"))
    if existing_path is None:
        monkeypatch.delenv("PATH", raising=False)
    else:
        monkeypatch.setenv("PATH", existing_path)
    assert linux_review.main(["check"]) == 2
    assert os.environ["PATH"] == str(prefix / "bin")
    assert shutil.which("untrusted-tool") is None


@pytest.mark.parametrize("caller_limit_kib", [None, 32768])
@pytest.mark.parametrize("environment_spelling", ["default", "alias", "canonical-alias"])
def test_executor_keeps_scanner_stack_finite_and_respects_caller_limit(
    linux_boundary: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caller_limit_kib: int | None, environment_spelling: str
) -> None:
    """Exercise the real pinned scanner's preexec policy inside the installer boundary."""
    # Read the actual parent environment before the simulated installer replaces
    # its prefix. Its fake uv deliberately does not provision a second scanner.
    expected_environment = Path(os.environ.get("DOTFILES_SEMGREP_ENVIRONMENT", REPOSITORY / "tooling/semgrep/.venv"))
    scanner_target = expected_environment
    alias_target = None
    if environment_spelling != "default":
        alias = tmp_path / "scanner environment"
        alias.symlink_to(expected_environment, target_is_directory=True)
        alias_target = alias.readlink()
        expected_environment = alias
        monkeypatch.setenv("DOTFILES_SEMGREP_ENVIRONMENT", str(alias))
    setup = run_installer(linux_boundary)
    assert setup.returncode == 0, setup.stderr
    executable_observation = "sys.executable"
    if environment_spelling == "canonical-alias":
        # Model macOS spelling on any POSIX host without resolving the venv's
        # interpreter symlink out of the scanner environment itself.
        executable_observation = "str(Path(sys.executable).parent.parent.resolve() / 'bin' / Path(sys.executable).name)"
    probe = (
        "import json, resource, sys; from pathlib import Path; from semgrep.core_runner import setrlimits_preexec_fn; "
        "before = resource.getrlimit(resource.RLIMIT_STACK); setrlimits_preexec_fn(); "
        "print(json.dumps({'before': before, 'after': resource.getrlimit(resource.RLIMIT_STACK), "
        f"'infinity': resource.RLIM_INFINITY, 'executable': {executable_observation}}}))"
    )
    scanner_python = Path(os.environ.get("DOTFILES_SEMGREP_ENVIRONMENT", REPOSITORY / "tooling/semgrep/.venv")) / "bin/python"
    argv = ["/bin/bash", str(REPOSITORY / "bin/linux-review.sh"), "exec", str(scanner_python), "-c", probe]
    if caller_limit_kib is not None:
        argv = ["/bin/bash", "-c", 'ulimit -HS -s "$1"; shift; exec "$@"', "scanner-stack-boundary", str(caller_limit_kib), *argv]
    result = subprocess.run(argv, env=linux_boundary, capture_output=True, text=True, check=False, timeout=30)  # noqa: S603 - fixed isolated boundary probe.
    assert result.returncode == 0, result.stderr
    limits = json.loads(result.stdout)
    assert Path(limits["executable"]).parent.parent.samefile(expected_environment)
    if environment_spelling != "default":
        assert expected_environment.is_symlink()
        assert expected_environment.readlink() == alias_target
        assert expected_environment.samefile(scanner_target)
    assert limits["before"][1] != limits["infinity"]
    assert 0 < limits["after"][0] <= limits["after"][1] <= 64 * 1024 * 1024
    if caller_limit_kib is not None:
        assert limits["before"][1] == limits["after"][1] == caller_limit_kib * 1024


@pytest.mark.parametrize(("version", "supported"), [("2.28", False), ("2.33", False), ("2.34", True)])
def test_installer_requires_the_locked_scanner_wheel_glibc(linux_boundary: dict[str, str], version: str, *, supported: bool) -> None:
    linux_boundary["FAKE_LIBC"] = f"glibc {version}"
    result = run_installer(linux_boundary)
    assert (result.returncode == 0) is supported, result.stderr
    if not supported:
        assert "locked Semgrep wheel requires >= 2.34" in result.stderr
        assert not Path(linux_boundary["DOWNLOAD_LOG"]).exists()


def test_plugin_failure_is_retained_as_failed_setup(linux_boundary: dict[str, str]) -> None:
    linux_boundary["PLUGIN_CHECK_EXIT_CODE"] = "17"
    result = run_installer(linux_boundary)
    assert result.returncode == 17
    assert "setup complete" not in result.stdout
    report_path = next(Path(linux_boundary["DOTFILES_REVIEW_ARTIFACTS"]).glob("setup-*/environment.json"))
    report = json.loads(report_path.read_text())
    assert report["status"] == "failed"
    assert report["exit_code"] == 17
    finished = json.loads((report_path.parent / "timing.jsonl").read_text().splitlines()[-1])
    assert finished["exit_code"] == 17


def test_setup_does_not_execute_from_temporary_storage(linux_boundary: dict[str, str]) -> None:
    """Model noexec temporary storage by denying execution bits on staged files."""
    chmod = Path(linux_boundary["PATH"]) / "chmod"
    real_chmod = chmod.resolve()
    chmod.unlink()
    executable(
        chmod,
        f'{shlex.quote(str(real_chmod))} "$@"\n'
        'if [[ "$1" == 700 && "$2" == "$DOTFILES_REVIEW_TMP"/install.*/executable ]]; then\n'
        f'  {shlex.quote(str(real_chmod))} 600 "$2"\nfi',
    )
    result = run_installer(linux_boundary)
    assert result.returncode == 0, result.stderr
    assert "setup complete" in result.stdout
    assert not list(Path(linux_boundary["DOTFILES_REVIEW_TMP"]).glob("install.*"))
    assert not list((Path(linux_boundary["DOTFILES_REVIEW_PREFIX"]) / "bin").glob(".*"))


@pytest.mark.parametrize("setting", ["missing-tool", "network", "checksum", "libc", "relative-directory"])
def test_failure_boundaries_never_claim_success(linux_boundary: dict[str, str], setting: str) -> None:
    if setting == "missing-tool":
        (Path(linux_boundary["PATH"]) / "stow").unlink()
    elif setting == "network":
        linux_boundary["BLOCK_NETWORK"] = "1"
    elif setting == "checksum":
        (Path(linux_boundary["RELEASES"]) / "uv-x86_64-unknown-linux-gnu.tar.gz.sha256").write_text("0" * 64 + "\n")
    elif setting == "libc":
        linux_boundary["FAKE_LIBC"] = "musl"
    else:
        linux_boundary["DOTFILES_REVIEW_CACHE"] = "relative-cache"
    result = run_installer(linux_boundary)
    assert result.returncode != 0
    assert "setup complete" not in result.stdout
    assert "linux-review:" in result.stderr
    assert not (Path(linux_boundary["DOTFILES_REVIEW_PREFIX"]) / "bin/uv").exists()


def test_check_cannot_download_missing_tools(linux_boundary: dict[str, str]) -> None:
    result = run_installer(linux_boundary, "check")
    assert result.returncode != 0
    assert "connected provisioning host" in result.stderr
    assert not Path(linux_boundary["DOWNLOAD_LOG"]).exists()


def test_skill_links_are_idempotent_and_collisions_preserve_existing_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "checkout-skills"
    source.mkdir()
    skill = source / "example"
    skill.mkdir()
    (skill / "SKILL.md").write_text("fixture")
    monkeypatch.setattr(linux_review, "SKILLS", source)
    target = tmp_path / "installed"
    linux_review.install_skills(target)
    linux_review.install_skills(target)
    linux_review.verify_skills(target)
    (target / "example").unlink()
    (target / "example").mkdir()
    marker = target / "example/private.txt"
    marker.write_text("preserve")
    with pytest.raises(ValueError, match="Skill collision"):
        linux_review.install_skills(target)
    assert marker.read_text() == "preserve"
    with pytest.raises(ValueError, match="Skill unavailable"):
        linux_review.verify_skills(target)


@pytest.mark.parametrize("outcome", [0, 1, 2, "timeout"])
def test_probe_records_only_safe_status_and_has_hard_bound(monkeypatch: pytest.MonkeyPatch, outcome: int | str) -> None:
    marker = b"private-secret-or-response"

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["timeout"] == 30
        assert kwargs["capture_output"] is True
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(argv, 30, output=marker, stderr=marker)
        assert isinstance(outcome, int)
        return subprocess.CompletedProcess(argv, outcome, marker, marker)

    monkeypatch.setattr(linux_review.subprocess, "run", run)
    result = linux_review.probe()
    assert result["status"] == ("passed" if outcome == 0 else "unavailable")
    assert marker.decode() not in json.dumps(result)


def test_inventory_excludes_environment_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "private-test-marker")
    document = linux_review.inventory()
    assert "private-test-marker" not in json.dumps(document)
    source = document["source"]
    assert isinstance(source, dict)
    assert source["commit"] != "unavailable"
    assert source["content_digest"].startswith("sha256:")


def test_inventory_identifies_the_independent_scanner_environment() -> None:
    scanner = linux_review.inventory()["scanner"]
    expected = Path(os.environ.get("DOTFILES_SEMGREP_ENVIRONMENT", REPOSITORY / "tooling/semgrep/.venv"))
    assert Path(scanner["environment"]).samefile(expected)
    assert scanner["python"]["executable"] is not None
    assert Path(scanner["python"]["executable"]).parent.parent.samefile(expected)
    assert scanner["python"]["identity"].startswith("Python 3.14.")
    assert scanner["python"]["available"]
    assert scanner["python"]["pin_matches"]
    project = tomllib.loads((REPOSITORY / "tooling/semgrep/pyproject.toml").read_text())["project"]
    expected_version = next(dependency.removeprefix("semgrep==") for dependency in project["dependencies"] if dependency.startswith("semgrep=="))
    assert scanner["semgrep"]["identity"] == f"semgrep {expected_version}"
    assert scanner["semgrep"]["available"]
    assert scanner["semgrep"]["pin_matches"]
    assert not Path(scanner["python"]["executable"]).parent.parent.samefile(Path(sys.executable).parent.parent)


def test_scanner_inventory_marks_a_missing_environment_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOTFILES_SEMGREP_ENVIRONMENT", str(tmp_path / "missing scanner"))
    scanner = linux_review.inventory()["scanner"]
    assert not scanner["python"]["available"]
    assert not scanner["semgrep"]["available"]


@pytest.mark.parametrize("observation", [None, [], "malformed", {"python_version": 314, "python_executable": None, "semgrep_version": 1182}])
def test_scanner_inventory_rejects_malformed_probe_output(monkeypatch: pytest.MonkeyPatch, observation: object) -> None:
    monkeypatch.setattr(linux_review, "command_output", lambda _argv: "not JSON" if observation == "malformed" else json.dumps(observation))
    scanner = linux_review.scanner_inventory()
    assert not scanner["python"]["available"]
    assert not scanner["semgrep"]["available"]


@pytest.mark.parametrize(("python_version", "semgrep_version", "missing"), [("3.13.9", "declared", "scanner Python"), ("3.14.9", "0.0.0", "Semgrep")])
def test_direct_check_distinguishes_scanner_pin_mismatch_from_unavailability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, python_version: str, semgrep_version: str, missing: str
) -> None:
    actual = linux_review.scanner_inventory()
    observation = {
        "python_executable": actual["python"]["executable"],
        "python_version": python_version,
        "semgrep_version": actual["semgrep"]["expected_version"] if semgrep_version == "declared" else semgrep_version,
        "private_environment_field": "private-marker-must-not-be-recorded",
    }
    original = linux_review.command_output
    scanner_python = str(Path(actual["environment"]) / "bin/python")
    monkeypatch.setattr(linux_review, "command_output", lambda argv: json.dumps(observation) if argv[0] == scanner_python else original(argv))
    monkeypatch.setenv("DOTFILES_REVIEW_ARTIFACTS", str(tmp_path / "artifacts"))
    assert linux_review.main(["check"]) == 2
    report_path = next((tmp_path / "artifacts").glob("check-*/environment.json"))
    report = json.loads(report_path.read_text())
    assert report["status"] == "unavailable"
    assert missing in report["diagnostic"]
    assert report["scanner"]["python"]["available"]
    assert report["scanner"]["semgrep"]["available"]
    assert not (report_path.parent / "launch.json").exists()
    assert "private-marker" not in report_path.read_text()


def test_empty_version_output_is_an_unavailable_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    original = linux_review.command_output

    def output(argv: list[str]) -> str:
        return "" if argv[-1] == "--version" else original(argv)

    monkeypatch.setattr(linux_review, "command_output", output)
    tools = linux_review.inventory()["tools"]
    assert isinstance(tools, dict)
    assert all(not tool["available"] for tool in tools.values())


@pytest.mark.parametrize("identity", ["1.2.3", "1.2.3-rc.1+build.2"])
def test_version_probe_preserves_cargo_suffixes(tmp_path: Path, identity: str) -> None:
    """Exercise the installer's actual probe without provisioning host tools."""
    tool = tmp_path / "tool"
    executable(tool, f"echo tool {identity}")
    source = (REPOSITORY / "bin/linux-review.sh").read_text()
    probe = "tool_version() {" + source.split("tool_version() {", 1)[1].split("\ninstall_release()", 1)[0]
    result = subprocess.run(  # noqa: S603 - isolated binary and the repository's read-only version probe.
        ["/bin/bash", "-c", probe + '\ntool_version "$1"', "probe", str(tool)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == identity


@pytest.mark.parametrize("actual", ["1.2.3", "1.2.3-rc.1+build.2", "1.2.3-rc.2+build.2"])
def test_inventory_compares_the_complete_tool_version(monkeypatch: pytest.MonkeyPatch, actual: str) -> None:
    expected = "1.2.3-rc.1+build.2"
    original = linux_review.command_output

    def output(argv: list[str]) -> str:
        if argv[-2:] == ["--evaluate", "dprint_version"]:
            return expected
        if Path(argv[0]).name == "dprint" and argv[-1] == "--version":
            return f"dprint {actual}"
        return original(argv)

    monkeypatch.setattr(linux_review, "command_output", output)
    tools = linux_review.inventory()["tools"]
    assert isinstance(tools, dict)
    assert tools["dprint"]["pin_matches"] is (actual == expected)


@pytest.mark.skipif(os.name != "posix", reason="POSIX byte filenames and newline filenames")
@pytest.mark.parametrize(
    "name",
    [
        b" leading.py",
        b"line\r\nbreak.py",
        pytest.param(
            b"non-utf8-\xff.py",
            marks=pytest.mark.skipif(sys.platform != "linux", reason="Native Linux filename bytes; this macOS test filesystem rejects invalid UTF-8 names"),
        ),
    ],
)
def test_source_digest_preserves_raw_git_filenames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: bytes) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    source = checkout / os.fsdecode(name)
    source.write_bytes(b"before")
    git = tmp_path / "git"
    listing = shlex.quote(f"import sys; sys.stdout.buffer.write({name + b'\0'!r})")
    executable(git, f'case "$1" in ls-files) exec {shlex.quote(sys.executable)} -c {listing} ;; rev-parse) echo {"a" * 40} ;; esac')
    monkeypatch.setattr(linux_review, "REPOSITORY", checkout)
    monkeypatch.setattr(linux_review.shutil, "which", lambda _: str(git))
    before = linux_review.source_identity()
    source.write_bytes(b"after")
    after = linux_review.source_identity()
    assert before["content_digest"] != after["content_digest"]


def test_failed_git_enumeration_cannot_publish_a_passing_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    index = tmp_path / "malformed-index"
    marker = "private-index-fixture"
    index.write_text(marker)
    monkeypatch.setenv("GIT_INDEX_FILE", str(index))
    monkeypatch.setenv("DOTFILES_REVIEW_ARTIFACTS", str(tmp_path / "artifacts"))
    assert linux_review.main(["smoke"]) == 2
    report_path = next((tmp_path / "artifacts").glob("smoke-*/environment.json"))
    report = json.loads(report_path.read_text())
    assert report["status"] == "unavailable"
    assert report["source"]["content_digest"] == "unavailable"
    assert not (report_path.parent / "graph").exists()
    assert marker not in report_path.read_text() + capsys.readouterr().err
