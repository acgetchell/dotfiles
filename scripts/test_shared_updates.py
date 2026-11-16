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


def test_python_environment_uses_repository_just_pin() -> None:
    just = Path(sys.executable).with_name("just.exe" if sys.platform == "win32" else "just")
    expected = subprocess.run(  # noqa: S603 - the environment's installed Just reads the repository pin.
        [str(just), "--evaluate", "just_version"], cwd=REPOSITORY, check=True, capture_output=True, text=True, timeout=10
    ).stdout.strip()
    assert version("rust-just") == expected
    actual = subprocess.run([str(just), "--version"], check=True, capture_output=True, text=True, timeout=10).stdout.strip()  # noqa: S603
    assert actual == f"just {expected}"


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
    sources = tomllib.loads((REPOSITORY / "dependency-sources.toml").read_text())
    assert sources["sources"]["tooling"]["version"] == version("research-repo-tools")
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
    ("overrides", "failure"), [(overrides, failure) for overrides in (False, True) for failure in (None, "check-uv", "update-python", "install-update")]
)
def test_update_orders_managers_and_stops_after_failures(tmp_path: Path, *, overrides: bool, failure: str | None) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copy2(REPOSITORY / "justfile", checkout)
    shutil.copy2(REPOSITORY / "pyproject.toml", checkout)
    (checkout / "bin").mkdir()
    for script in ("setup-profile.sh", "platform-profile.sh"):
        shutil.copy2(REPOSITORY / "bin" / script, checkout / "bin" / script)
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
if name == "uname":
    # Exercise the macOS manager contract on every test host through the real dispatcher.
    print({{"-s": "Darwin", "-m": "x86_64"}}[args[0]])
elif name == "uv" and args == ["--version"]:
    print("uv " + tomllib.loads(manifest.read_text())["tool"]["uv"]["required-version"].removeprefix("=="))
elif name == "cargo-install-update" and args == ["--version"]:
    print("cargo-install-update 22.1.1")
elif name == "brew" and args in (["--prefix", "uv"], ["--prefix", "icu4c"]):
    print({str(tmp_path)!r})
else:
    with Path({str(log)!r}).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps([name, *args]) + "\\n")
    if {failure!r} is not None and {failure!r} in args:
        raise SystemExit(23)
    if name == "uv" and args[-2:] == ["deps", "update-uv"]:
        manifest.write_text(manifest.read_text().replace({f'required-version = "=={uv_version}"'!r}, {f'required-version = "=={upgraded_uv}"'!r}))
"""
    for name in ("brew", "uv", "cargo", "cargo-install-update", "uname"):
        executable = binaries / name
        executable.write_text(body, encoding="utf-8")
        executable.chmod(0o755)
    just = shutil.which("just")
    assert just is not None
    environment = {**os.environ, "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run([just, "update"], cwd=checkout, env=environment, check=False, capture_output=True, text=True, timeout=30)  # noqa: S603
    assert log.is_file(), result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    stages = [
        call[call.index("deps") + 1] if "deps" in call else call[-1] if "research-repo-tools" in call else "brew" if call[0] == "brew" else call[1]
        for call in calls
    ]
    expected = ["check-uv", "brew", "update-uv", "check-uv", "update-python", "install-update", "update-tools", "upgrade"]
    if failure is not None:
        expected = expected[: expected.index(failure) + 1]
    assert (result.returncode == 0) == (failure is None), result.stderr
    assert stages == expected
    expected_manifest = original_manifest
    if "update-uv" in stages:
        expected_manifest = expected_manifest.replace(f'required-version = "=={uv_version}"', f'required-version = "=={upgraded_uv}"')
    assert manifest.read_text() == expected_manifest
    if "update-python" in stages:
        call = next(call for call in calls if "update-python" in call)
        assert call[-1] == "--all-projects"
        assert "--only-group" in call
        assert "tooling" in call
        assert "--inexact" in call
    if "install-update" in stages:
        assert ["cargo", "install-update", "-a", "--locked"] in calls


@pytest.mark.parametrize("state", ["missing", "broken", "repair-fails"])
def test_cargo_update_repairs_its_updater_before_upgrading_tools(tmp_path: Path, state: str) -> None:
    for name in ("justfile", "pyproject.toml"):
        shutil.copy2(REPOSITORY / name, tmp_path)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (tmp_path / "lib/pkgconfig").mkdir(parents=True)
    site_pkgconfig = tmp_path / "site-pkgconfig"
    log = tmp_path / "cargo-calls.jsonl"
    updater = binaries / "cargo-install-update"
    if state != "missing":
        updater.write_text("#!/bin/sh\nexit 134\n")
        updater.chmod(0o700)
    body = f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
name, args = Path(sys.argv[0]).name, sys.argv[1:]
if name == "brew":
    print({str(tmp_path)!r})
elif name == "cargo":
    with Path({str(log)!r}).open("a") as stream:
        stream.write(json.dumps({{"argv": args, "pkg_config_path": os.environ.get("PKG_CONFIG_PATH")}}) + "\\n")
    if args[0] == "install":
        if {state!r} == "repair-fails":
            sys.exit(23)
        updater = Path({str(updater)!r})
        updater.write_text("#!/bin/sh\\necho cargo-install-update repaired\\n")
        updater.chmod(0o700)
"""
    for name in ("brew", "uv", "cargo"):
        executable = binaries / name
        executable.write_text(body)
        executable.chmod(0o700)
    just = shutil.which("just")
    assert just is not None
    pin = subprocess.run(  # noqa: S603 - resolve the consumer's actual updater pin.
        [just, "--evaluate", "cargo_update_version"], cwd=tmp_path, capture_output=True, text=True, check=True, timeout=10
    ).stdout.strip()
    (binaries / "just").symlink_to(just)
    result = subprocess.run(  # noqa: S603 - real update recipe with isolated manager stand-ins.
        [just, "update-cargo-tools"],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{binaries}{os.pathsep}/usr/bin{os.pathsep}/bin", "PKG_CONFIG_PATH": str(site_pkgconfig)},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert log.is_file(), result.stderr
    events = [json.loads(line) for line in log.read_text().splitlines()]
    calls = [event["argv"] for event in events]
    assert events[0]["pkg_config_path"] == str(site_pkgconfig)
    assert calls[0] == ["install", "--locked", "--force", "cargo-update", "--version", pin, "--features", "vendored-openssl"]
    if state == "repair-fails":
        assert result.returncode != 0
        assert len(calls) == 1
        assert updater.read_text() == "#!/bin/sh\nexit 134\n"
    else:
        assert result.returncode == 0, result.stderr
        assert calls == [calls[0], ["install-update", "-a", "--locked"]]
        assert events[1]["pkg_config_path"] == f"{site_pkgconfig}{os.pathsep}{tmp_path / 'lib/pkgconfig'}"
        assert "repaired" in updater.read_text()
