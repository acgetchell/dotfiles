"""Exercise bootstrap installation with isolated host-tool stand-ins."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def write_executable(binaries: Path, name: str, body: str) -> None:
    target = binaries / name
    target.write_text(f"#!/bin/bash\nset -euo pipefail\n{body}\n", encoding="utf-8")
    target.chmod(0o755)


def prepare_legacy_skill(tmp_path: Path, skill: Path) -> None:
    legacy = tmp_path / ".agents" / "skills" / "bootstrap-test"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").symlink_to(os.path.relpath(skill / "SKILL.md", legacy))
    (legacy / "__pycache__").mkdir()
    (legacy / "__pycache__" / "old.pyc").write_bytes(b"bytecode")


def prepare_omz(tmp_path: Path, omz_state: str) -> Path:
    omz = tmp_path / ".oh-my-zsh"
    if omz_state != "missing":
        omz.mkdir()
        (omz / "custom.txt").write_text("preserve", encoding="utf-8")
    if omz_state == "installed":
        (omz / "oh-my-zsh.sh").write_text("existing", encoding="utf-8")

    return omz


@pytest.mark.parametrize("omz_state", ["missing", "installed", "incomplete"])
@pytest.mark.parametrize("installed_version", [None, "1.0.0", "22.1.1"])
def test_bootstrap_installs_updater_by_package_and_checks_its_executable(tmp_path: Path, installed_version: str | None, omz_state: str) -> None:
    repository = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "dotfiles"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (checkout / "bin").mkdir(parents=True)
    shutil.copy2(repository / "bin" / "resolve-just-version.sh", checkout / "bin")
    shutil.copy2(repository / "bin" / "restow-agents.sh", checkout / "bin")
    source = (repository / "justfile").read_text(encoding="utf-8")
    fixture = "\n".join('cargo_update_version := "22.1.1"' if line.startswith("cargo_update_version :=") else line for line in source.splitlines())
    (checkout / "justfile").write_text(f"{fixture}\n", encoding="utf-8")
    just = shutil.which("just")
    assert just is not None
    (binaries / "just").symlink_to(just)
    stow = shutil.which("stow")
    assert stow is not None
    (binaries / "stow").symlink_to(stow)
    skill = checkout / "agents" / ".agents" / "skills" / "bootstrap-test"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: bootstrap-test\ndescription: Test fresh-machine skill provisioning.\n---\n", encoding="utf-8")
    prepare_legacy_skill(tmp_path, skill)
    install_log = tmp_path / "installs"
    omz = prepare_omz(tmp_path, omz_state)

    write_executable(
        binaries,
        "git",
        '[[ "$1" == clone && "$2" == --depth=1 && "$3" == https://github.com/ohmyzsh/ohmyzsh.git ]]\nmkdir "$4"\nprintf "installed" > "$4/oh-my-zsh.sh"',
    )
    write_executable(binaries, "brew", 'if [[ "${1:-}" == --prefix ]]; then printf "%s\\n" "$FAKE_PREFIX"; fi')
    write_executable(
        binaries,
        "cargo",
        'printf "%s\\n" "$*" >> "$INSTALL_LOG"\n'
        '[[ "$*" == "install --locked --force cargo-update --version 22.1.1" ]]\n'
        "printf '#!/bin/bash\\necho cargo-install-update 22.1.1\\n' > \"$FAKE_PREFIX/bin/cargo-install-update\"\n"
        'chmod +x "$FAKE_PREFIX/bin/cargo-install-update"',
    )
    for tool in ("dprint", "rumdl", "zizmor"):
        version = subprocess.run(  # noqa: S603 - resolved Just executable and fixed pin queries.
            [just, "--justfile", str(checkout / "justfile"), "--evaluate", f"{tool}_version"], check=True, capture_output=True, text=True
        ).stdout.strip()
        write_executable(binaries, tool, f"echo {tool} {version}")
    if installed_version is not None:
        write_executable(binaries, "cargo-install-update", f"echo cargo-install-update {installed_version}")
    environment = {
        **os.environ,
        "PATH": f"{binaries}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "DOTFILES_DIR": str(checkout),
        "FAKE_PREFIX": str(tmp_path),
        "INSTALL_LOG": str(install_log),
    }

    if omz_state == "incomplete":
        result = subprocess.run(  # noqa: S603 - isolated bootstrap fixture.
            ["/bin/bash", str(repository / "bin" / "bootstrap.sh")], check=False, capture_output=True, text=True, env=environment
        )
        assert result.returncode != 0
        assert "Incomplete Oh My Zsh" in result.stderr
        assert (omz / "custom.txt").read_text(encoding="utf-8") == "preserve"
        return

    for _ in range(2):
        subprocess.run(  # noqa: S603 - repository bootstrap with isolated fake host tools.
            ["/bin/bash", str(repository / "bin" / "bootstrap.sh")], check=True, capture_output=True, text=True, env=environment
        )

    if installed_version == "22.1.1":
        assert not install_log.exists()
    else:
        assert install_log.read_text(encoding="utf-8").splitlines() == ["install --locked --force cargo-update --version 22.1.1"]
    manifest = tmp_path / ".agents" / "skills" / "bootstrap-test" / "SKILL.md"
    assert manifest.is_file()
    assert not manifest.is_symlink()
    assert manifest.resolve() == skill / "SKILL.md"

    assert (omz / "oh-my-zsh.sh").read_text(encoding="utf-8") == ("existing" if omz_state == "installed" else "installed")
    if omz_state == "installed":
        assert (omz / "custom.txt").read_text(encoding="utf-8") == "preserve"
