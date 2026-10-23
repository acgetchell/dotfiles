"""Record a portable review environment and run explicit, credential-free checks."""

__lazy_modules__ = ("argparse", "hashlib", "platform", "re", "shutil", "subprocess", "tempfile", "time", "tomllib")

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from typing import TypedDict

REPOSITORY = Path(__file__).resolve().parents[1]
SKILLS = REPOSITORY / "agents/.agents/skills"
TIMING = SKILLS / "review-validator/scripts/run_timed.py"
SMOKE = SKILLS / "review-graph/scripts/review_graph_smoke.py"


class SourceIdentity(TypedDict, closed=True):
    """Exact source identities without additional untracked metadata fields."""

    commit: str
    content_digest: str


class ToolIdentity(TypedDict, closed=True):
    """Allowlisted identity and availability fields for one installed tool."""

    executable: str | None
    identity: str
    expected_version: str | None
    available: bool
    pin_matches: bool


class ToolIdentities(TypedDict, extra_items=ToolIdentity):
    """Dynamic tool names whose values retain the same checked shape."""


class PythonIdentity(TypedDict, closed=True):
    """The executing interpreter's public identity."""

    version: str
    executable: str


class ScannerIdentity(TypedDict, closed=True):
    """The independently selected scanner environment and its installed pins."""

    environment: str
    python: ToolIdentity
    semgrep: ToolIdentity


class EnvironmentInventory(TypedDict, closed=True):
    """Stable environment-report fields, independent of the invoking host."""

    schema_version: int
    source: SourceIdentity
    system: str
    distribution: dict[str, str]
    architecture: str
    libc: list[str]
    shell: str
    python: PythonIdentity
    tools: ToolIdentities
    scanner: ScannerIdentity
    verification_scope: str


class ProbeResult(TypedDict, closed=True):
    """Bounded probe outcome with no response bodies or caller-supplied errors."""

    status: str
    reason: str
    exit_code: int | None
    elapsed_seconds: float


def command_output(argv: list[str]) -> str:
    """Read only fixed public tool identities; suppress arbitrary failure output."""
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=10, cwd=REPOSITORY)  # noqa: S603
    except OSError, subprocess.SubprocessError:
        return "unavailable"
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def source_identity() -> SourceIdentity:
    """Bind local evidence to HEAD and all nonignored checkout bytes without Git writes."""
    git = shutil.which("git")
    if git is None:
        msg = "Source identity unavailable; Git is required."
        raise ValueError(msg)
    try:
        result = subprocess.run(  # noqa: S603 - fixed, read-only Git enumeration; preserve raw filename bytes.
            [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"], check=True, capture_output=True, timeout=10, cwd=REPOSITORY
        )
    except OSError, subprocess.SubprocessError:
        msg = "Source identity unavailable; Git file enumeration failed."
        raise ValueError(msg) from None
    if result.stdout and not result.stdout.endswith(b"\0"):
        msg = "Source identity unavailable; Git file listing is incomplete."
        raise ValueError(msg)
    commit = command_output([git, "rev-parse", "HEAD"])
    if not commit or commit == "unavailable":
        msg = "Source identity unavailable; Git HEAD could not be read."
        raise ValueError(msg)
    digest = hashlib.sha256()
    for name in sorted(set(result.stdout.split(b"\0")) - {b""}):
        path = REPOSITORY / os.fsdecode(name)
        digest.update(name + b"\0")
        if path.is_symlink():
            content = os.fsencode(path.readlink())
        elif path.is_file():
            content = path.read_bytes()
        else:
            content = b"missing"
        digest.update(str(len(content)).encode() + b"\0" + content)
    return {"commit": commit, "content_digest": f"sha256:{digest.hexdigest()}"}


def scanner_inventory() -> ScannerIdentity:
    """Probe the configured scanner interpreter, never an ambient PATH entry."""
    project = REPOSITORY / "tooling/semgrep"
    environment = Path(os.environ.get("DOTFILES_SEMGREP_ENVIRONMENT", project / ".venv"))
    binaries = environment / ("Scripts" if os.name == "nt" else "bin")
    python = binaries / ("python.exe" if os.name == "nt" else "python")
    semgrep = binaries / ("semgrep.exe" if os.name == "nt" else "semgrep")
    selector = (project / ".python-version").read_text().strip()
    dependencies = tomllib.loads((project / "pyproject.toml").read_text())["project"]["dependencies"]
    expected = next((dependency.removeprefix("semgrep==") for dependency in dependencies if dependency.startswith("semgrep==")), None)
    probe = (
        "import importlib.metadata as metadata, json, platform, sys\n"
        "try: version = metadata.version('semgrep')\n"
        "except metadata.PackageNotFoundError: version = None\n"
        "print(json.dumps({'python_executable': sys.executable, 'python_version': platform.python_version(), 'semgrep_version': version}))\n"
    )
    try:
        observed = json.loads(command_output([str(python), "-I", "-c", probe]))
    except ValueError:
        observed = {}
    if not isinstance(observed, dict):
        observed = {}
    python_version = observed.get("python_version")
    python_executable = observed.get("python_executable")
    semgrep_version = observed.get("semgrep_version")
    python_available = (
        python.is_file() and isinstance(python_version, str) and bool(python_version) and isinstance(python_executable, str) and bool(python_executable)
    )
    semgrep_available = semgrep.is_file() and isinstance(semgrep_version, str) and bool(semgrep_version)
    version = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", python_version) if isinstance(python_version, str) else None
    return {
        "environment": str(environment),
        "python": {
            "executable": python_executable if python_available else None,
            "identity": f"Python {python_version}" if python_available else "unavailable",
            "expected_version": selector,
            "available": python_available,
            "pin_matches": bool(python_available and version and list(version.groups())[: len(selector.split("."))] == selector.split(".")),
        },
        "semgrep": {
            "executable": str(semgrep) if semgrep.is_file() else None,
            "identity": f"semgrep {semgrep_version}" if semgrep_available else "unavailable",
            "expected_version": expected,
            "available": semgrep_available,
            "pin_matches": bool(semgrep_available and expected and semgrep_version == expected),
        },
    }


def inventory() -> EnvironmentInventory:
    """Record allowlisted host/tool fields, never the environment or credentials."""
    versions = tomllib.loads((REPOSITORY / "pyproject.toml").read_text())
    expected = {"uv": versions["tool"]["uv"]["required-version"].removeprefix("==")}
    just = shutil.which("just")
    for name in ("just", "dprint", "rumdl"):
        expected[name] = command_output([just, "--evaluate", f"{name}_version"]) if just is not None else "unavailable"
    tools: ToolIdentities = {}
    for name in ("uv", "just", "dprint", "rumdl", "git", "bash", "zsh", "stow", "rustc", "cargo"):
        executable = shutil.which(name)
        lines = command_output([executable, "--version"]).splitlines() if executable is not None else []
        identity = next(iter(lines), "unavailable")
        match = re.search(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", identity)
        tools[name] = {
            "executable": executable,
            "identity": identity,
            "expected_version": expected.get(name),
            "available": executable is not None and identity != "unavailable",
            "pin_matches": name not in expected or bool(match and match.group() == expected[name]),
        }
    return {
        "schema_version": 1,
        "source": source_identity(),
        "system": platform.system(),
        "distribution": platform.freedesktop_os_release() if sys.platform == "linux" else {},
        "architecture": platform.machine(),
        "libc": list(platform.libc_ver()),
        "shell": os.environ.get("SHELL", "unspecified"),
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "tools": tools,
        "scanner": scanner_inventory(),
        "verification_scope": "this host only; cloud and HPC require separate native runs",
    }


def verify_rust_version(identity: str) -> None:
    """Require the minimum compiler version used by the offline Rust fixtures."""
    version = re.match(r"rustc ([0-9]+)\.([0-9]+)\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?(?:\s|$)", identity)
    if version is None or (int(version.group(1)), int(version.group(2))) < (1, 85):
        msg = "Rust >= 1.85 required for offline review fixtures. Load a compatible site toolchain."
        raise ValueError(msg)


def install_skills(destination: Path) -> None:
    """Link complete skill directories, refusing to replace unrelated installations."""
    destination.mkdir(parents=True, exist_ok=True)
    sources = sorted(path.parent for path in SKILLS.glob("*/SKILL.md"))
    for source in sources:
        target = destination / source.name
        if (target.exists() or target.is_symlink()) and (not target.is_symlink() or target.resolve() != source.resolve()):
            msg = f"Skill collision: {source.name}; select an isolated DOTFILES_REVIEW_SKILLS_DIR or resolve the existing installation."
            raise ValueError(msg)
    for source in sources:
        target = destination / source.name
        if not target.is_symlink():
            target.symlink_to(source.resolve(), target_is_directory=True)


def verify_skills(destination: Path) -> None:
    """Require discoverable directory links from this checkout."""
    for source in sorted(path.parent for path in SKILLS.glob("*/SKILL.md")):
        target = destination / source.name
        if not target.is_symlink() or target.resolve() != source.resolve() or (target / "SKILL.md").is_symlink():
            msg = f"Skill unavailable: {source.name}; rerun connected setup with this skill directory."
            raise ValueError(msg)


def run_timed(argv: list[str], output: Path) -> int:
    """Execute through #89's helper and retain the exact launch and timing receipt."""
    launch = output / "launch.json"
    launch.write_text(json.dumps({"schema_version": 1, "argv": argv, "working_directory": str(REPOSITORY)}) + "\n")
    return subprocess.run(  # noqa: S603 - fixed commands supplied by this command surface.
        [sys.executable, str(TIMING), "--input", str(launch), "--receipt", str(output / "timing.jsonl")], check=False
    ).returncode


def probe() -> ProbeResult:
    """Bound the existing safe TypeSafe probe without publishing response/error bodies."""
    started = time.monotonic()
    try:
        result = subprocess.run(  # noqa: S603 - fixed credential-safe probe, no input repository content.
            [sys.executable, str(REPOSITORY / "scripts/typesafe_check.py")], check=False, capture_output=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "reason": "TypeSafe probe exceeded 30 seconds", "exit_code": None, "elapsed_seconds": time.monotonic() - started}
    except OSError:
        return {"status": "unavailable", "reason": "TypeSafe probe could not launch", "exit_code": None, "elapsed_seconds": time.monotonic() - started}
    return {
        "status": "passed" if result.returncode == 0 else "unavailable",
        "reason": {0: "bounded authentication probe passed", 2: "credential missing, unresolved, or invalid"}.get(
            result.returncode, "network, authentication, or response failure; details withheld"
        ),
        "exit_code": result.returncode,
        "elapsed_seconds": time.monotonic() - started,
    }


def main(argv: list[str] | None = None) -> int:
    """Keep provisioning, offline checks, protocol smoke, and live authentication separate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("setup", "check", "smoke", "probe"))
    args = parser.parse_args(argv)
    # uv prepends the Python environment, whose transitive tools can shadow our pins.
    if prefix := os.environ.get("DOTFILES_REVIEW_PREFIX", ""):
        existing_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(Path(prefix) / "bin") + (os.pathsep + existing_path if existing_path else "")
    root = Path(os.environ.get("DOTFILES_REVIEW_ARTIFACTS", REPOSITORY / "target/linux-review")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=f"{args.mode}-", dir=root))
    output.chmod(0o700)
    report: dict[str, object] = {
        "schema_version": 1,
        "mode": args.mode,
        "status": "incomplete",
        "artifact_directory": str(output),
        "source": {"commit": "unavailable", "content_digest": "unavailable"},
    }
    code = 2
    try:
        environment = inventory()
        report.update(environment)
        tools = environment["tools"]
        required_tools = {**tools, "scanner Python": environment["scanner"]["python"], "Semgrep": environment["scanner"]["semgrep"]}
        missing = [name for name, tool in required_tools.items() if not tool["available"] or not tool["pin_matches"]]
        if missing:
            msg = f"Required tools unavailable or incorrectly pinned: {', '.join(missing)}. Load site modules or rerun connected setup."
            raise ValueError(msg)
        verify_rust_version(tools["rustc"]["identity"])
        destination = Path(os.environ.get("DOTFILES_REVIEW_SKILLS_DIR", SKILLS))
        if args.mode == "setup":
            install_skills(destination)
            # Warm the pinned formatter plugin before publishing setup success.
            code = run_timed([str(shutil.which("just")), "yaml-fmt-check"], output)
        else:
            if destination != SKILLS:
                verify_skills(destination)
            if args.mode == "probe":
                report["typesafe"] = result = probe()
                code = 0 if result["status"] == "passed" else 1
            elif args.mode == "check":
                code = run_timed([str(shutil.which("just")), "ci"], output)
            else:
                code = run_timed([sys.executable, str(SMOKE), "--output", str(output / "graph")], output)
        report["status"] = "passed" if code == 0 else "failed"
    except ValueError as error:
        report["status"] = "unavailable"
        report["diagnostic"] = str(error)
        print(f"linux-review: {error}", file=sys.stderr)
    except OSError:
        # Do not publish arbitrary exception strings from tools or paths.
        report["status"] = "unavailable"
        print("linux-review: environment or skill directory unavailable; check tool pins and skill collisions, then rerun setup.", file=sys.stderr)
    report["exit_code"] = code
    (output / "environment.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(output / "environment.json")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
