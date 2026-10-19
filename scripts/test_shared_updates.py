"""Consumer integration checks for shared updater configuration and recipes."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]


def run_shared(root: Path, action: str) -> subprocess.CompletedProcess[str]:
    """Exercise the installed distribution's supported CLI in a consumer fixture."""
    command = shutil.which("research-repo-tools")
    assert command is not None
    return subprocess.run(  # noqa: S603
        [command, "--root", str(root), "deps", action], check=True, capture_output=True, text=True, cwd=root, timeout=60
    )


def test_shared_updater_reconciles_dotfiles_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configuration = tomllib.loads((REPOSITORY / "pyproject.toml").read_text())
    mapping = configuration["tool"]["research-repo-tools"]["deps"]["tools"]
    assert configuration["dependency-groups"]["tooling"] == [f"research-repo-tools=={version('research-repo-tools')}"]
    assert {"include-group": "tooling"} in configuration["dependency-groups"]["dev"]
    # Use the real files so stale mappings or incompatible Just syntax fail here.
    shutil.copy2(REPOSITORY / "pyproject.toml", tmp_path)
    shutil.copy2(REPOSITORY / "justfile", tmp_path)
    inventory = "".join(f"{tool} v1.2.3:\n    {tool}\n" for tool in mapping.values() if tool != "uv")
    cargo = tmp_path / "cargo"
    cargo.write_text(f"#!{sys.executable}\nprint({inventory!r})\n", encoding="utf-8")
    cargo.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    run_shared(tmp_path, "update-tools")

    just = shutil.which("just")
    assert just is not None
    pins = json.loads(subprocess.run([just, "--dump", "--dump-format", "json"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout)  # noqa: S603
    for pin, tool in mapping.items():
        expected = "1.2.3" if tool != "uv" else subprocess.run(["uv", "--version"], check=True, capture_output=True, text=True).stdout.split()[1]  # noqa: S607
        assert pins["assignments"][pin]["value"] == expected


@pytest.mark.parametrize(
    ("overrides", "failure"),
    [(overrides, failure) for overrides in (False, True) for failure in (None, "check-uv", "python-preflight", "lock", "sync", "install-update")]
    + [(False, "update-python")],
)
def test_update_orders_managers_and_stops_after_failures(tmp_path: Path, *, overrides: bool, failure: str | None) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copy2(REPOSITORY / "justfile", checkout)
    shutil.copy2(REPOSITORY / "pyproject.toml", checkout)
    (checkout / "scripts").mkdir()
    shutil.copy2(REPOSITORY / "scripts/python_update_preflight.py", checkout / "scripts")
    manifest = checkout / "pyproject.toml"
    uv_version = tomllib.loads(manifest.read_text())["tool"]["uv"]["required-version"].removeprefix("==")
    if not overrides:
        # These manager-ordering scenarios need only the pin and no resolver overrides.
        manifest.write_text(f'[tool.uv]\nrequired-version = "=={uv_version}"\n')
    original_manifest = manifest.read_text()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "calls.jsonl"
    major, minor, patch = uv_version.split(".")
    upgraded_uv = f"{major}.{minor}.{int(patch) + 1}"
    # Host managers are stand-ins; execute the real Just recipes, including nested calls.
    body = f"""#!{sys.executable}
import json, os, subprocess, sys, tomllib
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
manifest = Path({str(checkout / "pyproject.toml")!r})
if name == "uv" and args == ["--version"]:
    print("uv " + tomllib.loads(manifest.read_text())["tool"]["uv"]["required-version"].removeprefix("=="))
elif name == "brew" and args == ["--prefix", "uv"]:
    print({str(tmp_path)!r})
else:
    with Path({str(log)!r}).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps([name, *args]) + "\\n")
    if name == "uv" and args == ["run", "--locked", "python", "scripts/python_update_preflight.py"]:
        if {failure!r} == "python-preflight":
            raise SystemExit(23)
        raise SystemExit(subprocess.run([sys.executable, args[-1]], check=False).returncode)
    if {failure!r} is not None and {failure!r} in args:
        raise SystemExit(23)
    if name == "uv" and args[-2:] == ["deps", "update-uv"]:
        manifest.write_text(manifest.read_text().replace({f'required-version = "=={uv_version}"'!r}, {f'required-version = "=={upgraded_uv}"'!r}))
"""
    for name in ("brew", "uv", "cargo", "cargo-install-update"):
        executable = binaries / name
        executable.write_text(body, encoding="utf-8")
        executable.chmod(0o755)
    just = shutil.which("just")
    assert just is not None
    environment = {**os.environ, "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run([just, "update"], cwd=checkout, env=environment, check=False, capture_output=True, text=True, timeout=30)  # noqa: S603
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    stages = [
        "python-preflight"
        if call == ["uv", "run", "--locked", "python", "scripts/python_update_preflight.py"]
        else call[-1]
        if "research-repo-tools" in call
        else "brew"
        if call[0] == "brew"
        else call[1]
        for call in calls
    ]
    expected = ["check-uv", "brew", "update-uv", "check-uv", "python-preflight", "update-python", "lock", "sync", "install-update", "update-tools", "upgrade"]
    if overrides:
        expected.remove("update-python")
    if failure is not None:
        expected = expected[: expected.index(failure) + 1]
    assert (result.returncode == 0) == (failure is None), result.stderr
    assert stages == expected
    expected_manifest = original_manifest
    if "update-uv" in stages:
        expected_manifest = expected_manifest.replace(f'required-version = "=={uv_version}"', f'required-version = "=={upgraded_uv}"')
    assert manifest.read_text() == expected_manifest
    if overrides:
        assert "update-python" not in stages
    if "lock" in stages:
        assert ["uv", "lock", "--upgrade"] in calls
    if "install-update" in stages:
        assert ["cargo", "install-update", "-a", "--locked"] in calls
    if "sync" in stages:
        assert ["uv", "sync", "--locked", "--group", "dev"] in calls
