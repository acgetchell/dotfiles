"""Tests for atomic repository tool-pin reconciliation."""

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


def test_parse_versions_accept_prerelease_and_build_metadata() -> None:
    version = "1.2.3-rc.1+build.5"

    installed = update_tool_pins.parse_installed_packages(cargo_output(override=("rumdl", version)))

    assert installed["rumdl"] == version
    assert update_tool_pins.parse_tool_version(f"uv {version} (build metadata)", "uv") == version


def test_parse_tool_version_rejects_ambiguous_output() -> None:
    with pytest.raises(ValueError, match="expected exactly one uv version, found 2"):
        update_tool_pins.parse_tool_version("uv 1.2.3 using runtime 3.14.0", "uv")
