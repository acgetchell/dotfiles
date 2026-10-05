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
    for name in ("git", "bash", "tar", "unzip", "sed", "head", "awk", "mkdir", "mktemp", "chmod", "cp", "mv", "rm", "dirname"):
        tool = shutil.which(name)
        assert tool
        (binaries / name).symlink_to(tool)
    # macOS need not install GNU coreutils to exercise the Linux boundary fixture.
    checksum = binaries / "sha256sum"
    checksum.write_text(
        f"#!{sys.executable}\nimport hashlib, sys\nfrom pathlib import Path\nprint(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest(), sys.argv[1])\n"
    )
    checksum.chmod(0o700)
    executable(binaries / "uname", 'case "$1" in -s) echo Linux ;; -m) echo x86_64 ;; esac')
    executable(binaries / "getconf", 'echo "${FAKE_LIBC:-glibc 2.39}"')
    for name in ("zsh", "stow"):
        executable(binaries / name, f"echo {name} fixture")
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
        'if [[ "$1" == run ]]; then\nshift\nwhile [[ "$1" == --* ]]; do shift; done\n'
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
    assert "run --locked --no-sync python scripts/linux_review.py setup" in calls
    assert "yaml-fmt-check" in calls
    reports = list(Path(linux_boundary["DOTFILES_REVIEW_ARTIFACTS"]).glob("setup-*/environment.json"))
    assert len(reports) == 2
    assert all(json.loads(path.read_text())["status"] == "passed" for path in reports)


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


def test_empty_version_output_is_an_unavailable_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    original = linux_review.command_output

    def output(argv: list[str]) -> str:
        return "" if argv[-1] == "--version" else original(argv)

    monkeypatch.setattr(linux_review, "command_output", output)
    tools = linux_review.inventory()["tools"]
    assert isinstance(tools, dict)
    assert all(not tool["available"] for tool in tools.values())


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
