"""Tests for atomic repository tool-pin reconciliation."""

import subprocess
from typing import TYPE_CHECKING

import pytest

import update_tool_pins

if TYPE_CHECKING:
    from pathlib import Path


def cargo_output(*, override: tuple[str, str] | None = None) -> str:
    """Return representative Cargo output for every managed package."""
    versions = dict.fromkeys(update_tool_pins.CARGO_PIN_TO_PACKAGE.values(), "1.2.3")
    if override is not None:
        versions[override[0]] = override[1]
    return "".join(f"{package} v{version}:\n    {package}\n" for package, version in versions.items())


def justfile_text(version: str = "1.2.3") -> str:
    """Return one assignment for every managed Just pin."""
    return "".join(f'{pin} := "{version}"\n' for pin in update_tool_pins.PIN_TO_TOOL)


def test_reconcile_pins_updates_cargo_and_uv_versions_atomically(tmp_path: Path) -> None:
    justfile = tmp_path / "justfile"
    justfile.write_text(justfile_text(), encoding="utf-8")

    changes = update_tool_pins.reconcile_pins(justfile, cargo_output(override=("rumdl", "2.0.0")), "uv 3.0.0")

    assert changes == {"rumdl_version": ("1.2.3", "2.0.0"), "uv_version": ("1.2.3", "3.0.0")}
    updated = justfile.read_text(encoding="utf-8")
    assert 'rumdl_version := "2.0.0"' in updated
    assert 'uv_version := "3.0.0"' in updated
    assert list(tmp_path.glob(".justfile.*")) == []


def test_reconcile_pins_rejects_missing_package_without_writing(tmp_path: Path) -> None:
    justfile = tmp_path / "justfile"
    original = justfile_text()
    justfile.write_text(original, encoding="utf-8")
    incomplete = cargo_output().replace("rumdl v1.2.3:\n    rumdl\n", "")

    with pytest.raises(ValueError, match="managed tool is not installed: rumdl"):
        update_tool_pins.reconcile_pins(justfile, incomplete, "uv 1.2.3")

    assert justfile.read_text(encoding="utf-8") == original


def test_update_pin_text_rejects_duplicate_assignment() -> None:
    duplicated = justfile_text() + 'rumdl_version := "1.2.3"\n'
    installed = dict.fromkeys(update_tool_pins.PIN_TO_TOOL.values(), "1.2.3")

    with pytest.raises(ValueError, match="expected exactly one rumdl_version assignment, found 2"):
        update_tool_pins.update_pin_text(duplicated, installed)


@pytest.mark.parametrize("version", ["1.2.3-rc.1", "1.2.3+build.5", "1.2.3-rc.1+build.5"])
def test_parse_installed_packages_rejects_nonstable_versions(version: str) -> None:
    with pytest.raises(ValueError, match=r"expected stable X\.Y\.Z"):
        update_tool_pins.parse_installed_packages(cargo_output(override=("rumdl", version)))


def test_parse_installed_packages_preserves_unmanaged_prerelease() -> None:
    output = f"{cargo_output()}unmanaged-tool v1.2.3-rc.1+build.5:\n    unmanaged-tool\n"

    installed = update_tool_pins.parse_installed_packages(output)

    assert installed["unmanaged-tool"] == "1.2.3-rc.1+build.5"


@pytest.mark.parametrize("version", ["1.2.3-rc.1", "1.2.3+build.5", "1.2.3-rc.1+build.5"])
def test_parse_tool_version_rejects_nonstable_versions(version: str) -> None:
    with pytest.raises(ValueError, match=r"expected stable X\.Y\.Z"):
        update_tool_pins.parse_tool_version(f"uv {version}", "uv")


def test_parse_tool_version_rejects_ambiguous_output() -> None:
    with pytest.raises(ValueError, match="expected exactly one uv version, found 2"):
        update_tool_pins.parse_tool_version("uv 1.2.3 using runtime 3.14.0", "uv")


@pytest.mark.parametrize(("output", "count"), [("uv 1.2.3.4", 0), ("uv release-1.2.3", 0), ("uv 1.2.3 (embedded 1.2.3)", 2)])
def test_parse_tool_version_rejects_partial_embedded_and_repeated_versions(output: str, count: int) -> None:
    with pytest.raises(ValueError, match=rf"expected exactly one uv version, found {count}"):
        update_tool_pins.parse_tool_version(output, "uv")


def test_reconcile_pins_preserves_file_when_uv_version_output_is_malformed(tmp_path: Path) -> None:
    justfile = tmp_path / "justfile"
    original = justfile_text()
    justfile.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="expected exactly one uv version"):
        update_tool_pins.reconcile_pins(justfile, cargo_output(), "uv 1.2.3.4")

    assert justfile.read_text(encoding="utf-8") == original


def test_main_uses_supplied_uv_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    justfile = tmp_path / "justfile"
    justfile.write_text(justfile_text(), encoding="utf-8")
    uv_executable = tmp_path / "homebrew-uv"
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        stdout = cargo_output() if command[:3] == ["cargo", "install", "--list"] else "uv 1.2.3"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(update_tool_pins.subprocess, "run", fake_run)

    result = update_tool_pins.main(["--justfile", str(justfile), "--uv-executable", str(uv_executable)])

    assert result == 0
    assert commands[1] == [str(uv_executable), "--version"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            subprocess.CalledProcessError(23, ["cargo"], stderr="\x1b[31mregistry unavailable\x1b[0m\nretry later"),
            "subprocess exited with status 23: registry unavailable retry later",
        ),
        (subprocess.TimeoutExpired(["cargo"], 30, stderr=b"registry request\ntimed out"), "subprocess timed out after 30 seconds: registry request timed out"),
        (OSError("permission denied\nwhile starting cargo"), "subprocess could not start: permission denied while starting cargo"),
    ],
)
def test_main_reports_sanitized_subprocess_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error: BaseException, expected: str
) -> None:
    justfile = tmp_path / "justfile"
    justfile.write_text(justfile_text(), encoding="utf-8")

    def fail_run(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        raise error

    monkeypatch.setattr(update_tool_pins.subprocess, "run", fail_run)

    result = update_tool_pins.main(["--justfile", str(justfile), "--uv-executable", "/opt/homebrew/bin/uv"])

    assert result == 1
    stderr = capsys.readouterr().err
    assert expected in stderr
    assert "\x1b" not in stderr
    assert "\nretry" not in stderr


def test_main_reports_bounded_value_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    justfile = tmp_path / "justfile"
    justfile.write_text(justfile_text(), encoding="utf-8")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        stdout = cargo_output() if command[:3] == ["cargo", "install", "--list"] else "uv 1.2.3"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(update_tool_pins.subprocess, "run", fake_run)
    monkeypatch.setattr(update_tool_pins, "reconcile_pins", lambda *_: (_ for _ in ()).throw(ValueError("x" * 800)))

    result = update_tool_pins.main(["--justfile", str(justfile), "--uv-executable", "/opt/homebrew/bin/uv"])

    assert result == 1
    stderr = capsys.readouterr().err
    assert "invalid tool state:" in stderr
    assert "…" in stderr
    assert len(stderr) <= update_tool_pins.DIAGNOSTIC_LIMIT + 80
