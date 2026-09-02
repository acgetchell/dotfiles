"""Reconcile repository tool pins with locally installed versions."""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CARGO_PIN_TO_PACKAGE = {"dprint_version": "dprint", "just_version": "just", "rumdl_version": "rumdl", "zizmor_version": "zizmor"}
PIN_TO_TOOL = {**CARGO_PIN_TO_PACKAGE, "uv_version": "uv"}
MANAGED_CARGO_PACKAGES = frozenset(CARGO_PIN_TO_PACKAGE.values())
PACKAGE_HEADER = re.compile(r"^(?P<package>[A-Za-z0-9_-]+) v(?P<version>[^\s:]+):$", re.MULTILINE)
SEMANTIC_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")
TOOL_VERSION = re.compile(rf"(?<![0-9A-Za-z_.+-])v?(?P<version>{SEMANTIC_VERSION.pattern})(?![0-9A-Za-z_.+-])")
STABLE_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]+")
DIAGNOSTIC_LIMIT = 400


def require_stable_version(version: str, tool: str) -> str:
    """Require the stable numeric version syntax consumed by repository tooling."""
    if STABLE_VERSION.fullmatch(version) is None:
        msg = f"invalid installed version for {tool}: {version}; expected stable X.Y.Z"
        raise ValueError(msg)
    return version


def parse_installed_packages(output: str) -> dict[str, str]:
    """Parse package versions from ``cargo install --list`` output."""
    packages: dict[str, str] = {}
    for match in PACKAGE_HEADER.finditer(output):
        package = match.group("package")
        version = match.group("version")
        if package in packages:
            msg = f"duplicate installed Cargo package: {package}"
            raise ValueError(msg)
        if package in MANAGED_CARGO_PACKAGES:
            packages[package] = require_stable_version(version, package)
        elif SEMANTIC_VERSION.fullmatch(version) is None:
            msg = f"invalid installed version for {package}: {version}"
            raise ValueError(msg)
        else:
            packages[package] = version
    return packages


def parse_tool_version(output: str, tool: str) -> str:
    """Extract one semantic version from a tool's version output."""
    versions = [match.group("version") for match in TOOL_VERSION.finditer(output)]
    if len(versions) != 1:
        msg = f"expected exactly one {tool} version, found {len(versions)}"
        raise ValueError(msg)
    return require_stable_version(versions[0], tool)


def read_stable_uv_version(uv_executable: Path) -> str:
    """Read and validate the stable version of the selected uv executable."""
    result = subprocess.run([str(uv_executable), "--version"], check=True, capture_output=True, text=True, timeout=30)  # noqa: S603
    return parse_tool_version(result.stdout, "uv")


def sanitize_diagnostic(value: object) -> str:
    """Return one bounded line without terminal control sequences."""
    text = value.decode(errors="replace") if isinstance(value, bytes) else str(value)
    text = ANSI_ESCAPE.sub("", text)
    text = CONTROL_CHARACTERS.sub(" ", text)
    text = " ".join(text.split())
    if len(text) > DIAGNOSTIC_LIMIT:
        return f"{text[: DIAGNOSTIC_LIMIT - 1]}…"
    return text


def format_failure(error: subprocess.CalledProcessError | subprocess.TimeoutExpired | OSError | ValueError) -> str:
    """Preserve safe, useful context for expected update failures."""
    if isinstance(error, subprocess.CalledProcessError):
        summary = f"subprocess exited with status {error.returncode}"
        detail = sanitize_diagnostic(error.stderr or error.stdout or "")
    elif isinstance(error, subprocess.TimeoutExpired):
        summary = f"subprocess timed out after {error.timeout} seconds"
        detail = sanitize_diagnostic(error.stderr or error.stdout or "")
    elif isinstance(error, OSError):
        summary = "subprocess could not start"
        detail = sanitize_diagnostic(error)
    else:
        summary = "invalid tool state"
        detail = sanitize_diagnostic(error)
    return f"{summary}: {detail}" if detail else summary


def update_pin_text(text: str, installed: dict[str, str]) -> tuple[str, dict[str, tuple[str, str]]]:
    """Return Just source with every managed pin reconciled exactly once."""
    updated = text
    changes: dict[str, tuple[str, str]] = {}
    for pin, tool in PIN_TO_TOOL.items():
        version = installed.get(tool)
        if version is None:
            msg = f"managed tool is not installed: {tool}"
            raise ValueError(msg)
        assignment = re.compile(rf'^(?P<prefix>{re.escape(pin)}\s*:=\s*")(?P<version>[^"]+)(?P<suffix>"\s*)$', re.MULTILINE)
        matches = list(assignment.finditer(updated))
        if len(matches) != 1:
            msg = f"expected exactly one {pin} assignment, found {len(matches)}"
            raise ValueError(msg)
        old_version = matches[0].group("version")
        if old_version == version:
            continue
        updated = assignment.sub(rf"\g<prefix>{version}\g<suffix>", updated, count=1)
        changes[pin] = (old_version, version)
    return updated, changes


def reconcile_pins(justfile: Path, cargo_output: str, uv_output: str) -> dict[str, tuple[str, str]]:
    """Atomically reconcile ``justfile`` and return changed pin versions."""
    installed = parse_installed_packages(cargo_output)
    installed["uv"] = parse_tool_version(uv_output, "uv")
    original = justfile.read_text(encoding="utf-8")
    updated, changes = update_pin_text(original, installed)
    if not changes:
        return changes

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{justfile.name}.", dir=justfile.parent, text=True)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
        temporary.chmod(justfile.stat().st_mode)
        temporary.replace(justfile)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return changes


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--justfile", type=Path, default=Path("justfile"), help="Just source containing repository tool pins")
    parser.add_argument("--uv-executable", type=Path, required=True, help="Verified Homebrew-managed uv executable")
    parser.add_argument("--check-uv-version", action="store_true", help="validate that uv reports exactly one stable X.Y.Z version without reconciling pins")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Reconcile managed tool pins from the local installations."""
    args = parse_args(argv)
    operation = "validate uv version" if args.check_uv_version else "update tool pins"
    try:
        uv_version = read_stable_uv_version(args.uv_executable)
        if args.check_uv_version:
            print(f"Homebrew-managed uv {uv_version} satisfies the stable X.Y.Z contract.")
            return 0
        cargo = subprocess.run(["cargo", "install", "--list"], check=True, capture_output=True, text=True, timeout=30)  # noqa: S607
        changes = reconcile_pins(args.justfile, cargo.stdout, uv_version)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as error:
        print(f"failed to {operation}: {format_failure(error)}", file=sys.stderr)
        return 1

    if not changes:
        print("Tool pins already match installed repository tools.")
        return 0
    for pin, (old_version, new_version) in changes.items():
        print(f"Updated {pin}: {old_version} -> {new_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
