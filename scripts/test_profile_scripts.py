"""Exercise profile repair and syntax checks through real shell entry points."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("shell", ["bash", "zsh"])
@pytest.mark.parametrize("state", ["missing", "broken-rustc", "broken-cargo", "old", "malformed", "minimum", "current"])
def test_shell_selects_only_a_usable_private_rust_toolchain(tmp_path: Path, shell: str, state: str) -> None:
    prefix = tmp_path / "private prefix"
    private_bin = prefix / "cargo/bin"
    private_bin.mkdir(parents=True)
    site_cargo, site_rust = tmp_path / "site cargo", tmp_path / "site rust"
    (site_cargo / "bin").mkdir(parents=True)
    if state != "missing":
        identity = {"old": "rustc 1.84.1", "malformed": "unrecognized compiler", "minimum": "rustc 1.85.0"}.get(state, "rustc 1.100.0")
        for name, output in (("rustc", identity), ("cargo", "cargo 1.100.0")):
            tool = private_bin / name
            tool.write_text(
                '#!/bin/sh\n[ "$RUSTUP_AUTO_INSTALL" = 0 ] || exit 99\n'
                '[ "$CARGO_HOME" = "$DOTFILES_REVIEW_PREFIX/cargo" ] || exit 98\n'
                '[ "$RUSTUP_HOME" = "$DOTFILES_REVIEW_PREFIX/rustup" ] || exit 97\n'
                f"printf '%s\\n' '{output}'\nexit {3 if state == 'broken-' + name else 0}\n"
            )
            tool.chmod(0o700)
    executable = shutil.which(shell)
    assert executable is not None
    original_path = f"{site_cargo / 'bin'}{os.pathsep}/usr/bin{os.pathsep}/bin"
    result = subprocess.run(  # noqa: S603 - real shells with isolated home and Rust stand-ins.
        [executable, "-f", "-c", '. "$1"; printf "%s\\n" "$PATH" "$CARGO_HOME" "$RUSTUP_HOME" "$RUSTUP_AUTO_INSTALL"', shell, str(ROOT / "zsh/.dotfiles-env")],
        env={
            "HOME": str(tmp_path / "home"),
            "PATH": original_path,
            "DOTFILES_REVIEW_PREFIX": str(prefix),
            "CARGO_HOME": str(site_cargo),
            "RUSTUP_HOME": str(site_rust),
            "RUSTUP_AUTO_INSTALL": "1",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    if state in {"minimum", "current"}:
        assert result.stdout.splitlines() == [f"{private_bin}{os.pathsep}{original_path}", str(prefix / "cargo"), str(prefix / "rustup"), "1"]
    else:
        assert result.stdout.splitlines() == [original_path, str(site_cargo), str(site_rust), "1"]


@pytest.mark.parametrize("probe_fails", [False, True])
def test_rust_probe_failure_enters_repair_without_touching_host_tools(tmp_path: Path, *, probe_fails: bool) -> None:
    checkout = tmp_path / "checkout with spaces"
    scripts, profiles, binaries = checkout / "bin", checkout / "profiles", tmp_path / "tools"
    for directory in (scripts, profiles, binaries):
        directory.mkdir(parents=True)
    shutil.copy2(ROOT / "bin/linux-rust.sh", scripts)
    shutil.copy2(ROOT / "profiles/linux-cloud.env", profiles)
    (scripts / "platform-profile.sh").write_text("select_profile() { :; }\n")
    body = rf"""#!{sys.executable}
import hashlib, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
if name == "rustc":
    print("rustc 1.85.0 (fixture)")
    sys.exit({3 if probe_fails else 0})
if name == "curl":
    output = Path(sys.argv[sys.argv.index("-o") + 1])
    if sys.argv[-3].endswith(".sha256"):
        output.write_text(hashlib.sha256((output.parent / "rustup-init").read_bytes()).hexdigest())
    else:
        output.write_text('#!/bin/sh\nprintf repaired > "$REPAIR_MARKER"\n')
elif name == "sha256sum":
    print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest() + "  " + sys.argv[1])
"""
    for name in ("rustc", "cargo", "curl", "sha256sum"):
        tool = binaries / name
        tool.write_text(body)
        tool.chmod(0o700)
    marker = tmp_path / "repair"
    bash = shutil.which("bash")
    assert bash is not None
    result = subprocess.run(  # noqa: S603 - real installer with all external tool effects isolated.
        [bash, str(scripts / "linux-rust.sh")],
        env={
            **os.environ,
            "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
            "DOTFILES_REVIEW_PREFIX": str(tmp_path / "prefix"),
            "REPAIR_MARKER": str(marker),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert marker.exists() is probe_fails
    if probe_fails:
        assert marker.read_text() == "repaired"


def test_shell_check_detects_syntax_error_after_first_file(tmp_path: Path) -> None:
    for name in ("justfile", "pyproject.toml"):
        shutil.copy2(ROOT / name, tmp_path)
    for directory in ("bin", "bash", "zsh"):
        (tmp_path / directory).mkdir()
    for name in ("bin/a.sh", "bash/.bashrc", "bash/.bash_profile", "zsh/.dotfiles-env"):
        (tmp_path / name).write_text(":\n")
    broken = tmp_path / "bin/z.sh"
    broken.write_text("if true; then\n")
    just = shutil.which("just")
    assert just is not None
    result = subprocess.run([just, "shell-check"], cwd=tmp_path, capture_output=True, text=True, check=False, timeout=10)  # noqa: S603
    assert result.returncode != 0
    assert "bin/z.sh" in result.stderr
    broken.write_text(":\n")
    result = subprocess.run([just, "shell-check"], cwd=tmp_path, capture_output=True, text=True, check=False, timeout=10)  # noqa: S603
    assert result.returncode == 0, result.stderr
