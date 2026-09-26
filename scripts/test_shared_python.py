"""Consumer contracts for shared Python inheritance and migration entry points."""

import json
import os
import shutil
import subprocess
import sys
from importlib.metadata import metadata
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("drift", [None, "selector", "requirement"])
def test_shared_baseline_checks_dotfiles_mirrors_without_repair(tmp_path: Path, drift: str | None) -> None:
    for name in ("pyproject.toml", ".python-version"):
        shutil.copy2(REPOSITORY / name, tmp_path)
    if drift == "selector":
        (tmp_path / ".python-version").write_text("3.13\n", encoding="utf-8")
    if drift == "requirement":
        manifest = tmp_path / "pyproject.toml"
        manifest.write_text(
            manifest.read_text().replace(f'requires-python = "{metadata("research-repo-tools")["Requires-Python"]}"', 'requires-python = ">=3.13"')
        )
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    executable = shutil.which("research-repo-tools")
    assert executable is not None
    result = subprocess.run(  # noqa: S603 - public installed CLI and an isolated consumer copy.
        [executable, "--root", str(tmp_path), "toolchain", "python-check"], capture_output=True, text=True, check=False, timeout=30
    )
    assert (result.returncode == 0) == (drift is None), result.stderr
    if drift:
        assert "shared Python drift" in result.stderr
    assert before == {path.name: path.read_bytes() for path in tmp_path.iterdir()}


@pytest.mark.parametrize(("recipe", "mode"), [("shared-python-plan", "--dry-run"), ("shared-python-update", "--apply")])
def test_migration_bootstraps_target_release_outside_old_environment(tmp_path: Path, recipe: str, mode: str) -> None:
    checkout = tmp_path / "consumer"
    checkout.mkdir()
    shutil.copy2(REPOSITORY / "justfile", checkout)
    shutil.copy2(REPOSITORY / "pyproject.toml", checkout)
    # A future migration must start even with an obsolete selector and no lock/venv.
    (checkout / ".python-version").write_text("3.13\n", encoding="utf-8")
    log = tmp_path / "invocation.json"
    launcher = tmp_path / "uvx"
    launcher.write_text(
        f"#!{sys.executable}\nimport json, sys\nfrom pathlib import Path\nPath({str(log)!r}).write_text(json.dumps(sys.argv[1:]))\nraise SystemExit(23)\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    just = shutil.which("just")
    assert just is not None
    result = subprocess.run(  # noqa: S603 - real recipe with an isolated noninstalling bootstrap stand-in.
        [just, recipe, "0.1.7"],
        cwd=checkout,
        env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert "exit code 23" in result.stderr
    assert json.loads(log.read_text()) == [
        "--no-config",
        "--isolated",
        "--managed-python",
        "--from",
        "research-repo-tools==0.1.7",
        "research-repo-tools",
        "toolchain",
        "adopt",
        mode,
    ]
    assert not (checkout / ".venv").exists()
