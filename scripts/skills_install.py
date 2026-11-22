"""Install complete skill directories without changing global instructions or settings."""

__lazy_modules__ = ("skill_validate",)

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from skill_validate import validate_skill

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "agents/.agents/skills"
ENVIRONMENT = SKILLS / "review-graph/scripts/review_graph_environment.py"
SELECTORS = (
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "UV_PROJECT_ENVIRONMENT",
    "UV_PYTHON",
    "UV_PROJECT",
    "UV_WORKING_DIR",
    "UV_CONFIG_FILE",
    "UV_SYSTEM_PYTHON",
    "UV_TARGET",
    "UV_PREFIX",
    "UV_OVERRIDE",
    "PYTHONHOME",
    "PYTHONPATH",
)


def skill_sources(source: Path) -> tuple[Path, ...]:
    """Require a nonempty, concrete source inventory."""
    sources = tuple(sorted(path.parent for path in source.glob("*/SKILL.md")))
    if not sources:
        raise ValueError(f"No skills found in {source}")
    for directory in sources:
        manifest = directory / "SKILL.md"
        if directory.is_symlink() or manifest.is_symlink() or not manifest.is_file():
            raise ValueError(f"Expected a regular SKILL.md in a concrete skill directory: {manifest}")
    return sources


def inspect_links(source: Path, destination: Path, *, installed: bool) -> tuple[Path, ...]:
    """Return sorted source skill directories after checking destination links.

    Preflight permits missing links. With installed=True, each skill must already
    have a directory link and a regular SKILL.md. Conflicts raise ValueError.
    """
    sources = skill_sources(source)
    if destination.resolve() == source.resolve() or destination.resolve().is_relative_to(source.resolve()):
        raise ValueError(f"Skill destination must be separate from its source: {destination}")
    if destination.is_symlink():
        raise ValueError(f"Skill destination is a directory link: {destination}")
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Skill destination is not a directory: {destination}")
    expected = {path.name for path in sources}
    if destination.is_dir():
        for entry in destination.iterdir():
            if entry.name not in expected and entry.is_symlink() and entry.resolve().is_relative_to(source.resolve()):
                raise ValueError(f"Stale managed skill link: {entry}; inspect and remove this obsolete link explicitly")
    for path in sources:
        target = destination / path.name
        present = target.exists() or target.is_symlink()
        if present and (not target.is_symlink() or target.resolve() != path.resolve()):
            problem = "Skill unavailable" if installed else "Skill collision"
            raise ValueError(f"{problem}: {target}; preserve existing content and choose another destination or resolve it manually")
        if installed and (not present or not (target / "SKILL.md").is_file() or (target / "SKILL.md").is_symlink()):
            raise ValueError(f"Skill unavailable: {target}; install complete directory links, not individual SKILL.md links")
    return sources


def link_skills(source: Path, destination: Path) -> None:
    """Create missing skill directory links after checking the whole destination.

    On a link-creation error, roll back links this call added that still point
    to their expected targets. Existing installations are preserved.
    """
    sources = inspect_links(source, destination, installed=False)
    destination.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for path in sources:
            target = destination / path.name
            expected = path.resolve()
            try:
                target.symlink_to(expected, target_is_directory=True)
            except FileExistsError:
                if not target.is_symlink() or target.resolve() != expected:
                    raise ValueError(f"Skill collision: {target}; preserve existing content and resolve it manually") from None
            else:
                created.append(target)
    except OSError, ValueError:
        # Roll back only links this invocation created; preserve all existing data.
        for target in reversed(created):
            if target.is_symlink() and target.resolve() == (source / target.name).resolve():
                target.unlink()
        raise


def locked_helper_versions() -> tuple[str, str]:
    """Read the locked research-repo-tools and markdown-it-py versions."""
    packages = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8")).get("package")
    if not isinstance(packages, list):
        msg = "uv.lock must contain a package list"
        raise TypeError(msg)

    def pinned_version(name: str) -> str:
        """Require one unambiguous, path-safe version for each helper dependency."""
        versions: set[str] = set()
        for package in packages:
            if isinstance(package, dict) and package.get("name") == name:
                value = package.get("version")
                if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", value):
                    raise ValueError(f"uv.lock must pin a valid version of {name}")
                versions.add(value)
        if len(versions) != 1:
            raise ValueError(f"uv.lock must pin exactly one version of {name}")
        return versions.pop()

    return pinned_version("research-repo-tools"), pinned_version("markdown-it-py")


def default_helper_directory() -> Path:
    """Select a directory for the pinned helper while preserving older runtimes."""
    prefix = Path(os.environ.get("DOTFILES_REVIEW_PREFIX", Path.home() / ".local/share/dotfiles-review"))
    helper_version, parser_version = locked_helper_versions()
    return prefix / f"helper-{helper_version}-markdown-it-{parser_version}"


def check_helper(helper: Path) -> dict[str, object]:
    """Probe the actual isolated interpreter with the graph's existing origin checks."""
    if not helper.is_absolute() or not helper.is_file():
        msg = f"Isolated helper Python is missing at {helper}; run just skills-helper-setup or Linux profile setup"
        raise ValueError(msg)
    helper_version, parser_version = locked_helper_versions()
    result = subprocess.run(  # noqa: S603 - explicit interpreter and repository-owned read-only probe.
        [str(helper), "-E", "-s", str(ENVIRONMENT), "--repository", str(ROOT), "--helper-version", helper_version, "--markdown-version", parser_version],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(f"Isolated helper check failed: {result.stderr.strip()}")
    origin: object = json.loads(result.stdout)
    if not isinstance(origin, dict):
        msg = "Invalid isolated helper origin report"
        raise TypeError(msg)
    report: dict[str, object] = {}
    for key, value in origin.items():
        if not isinstance(key, str):
            msg = "Isolated helper origin report keys must be strings"
            raise TypeError(msg)
        report[key] = value
    required = {"helper_version", "executable", "prefix", "package", "distribution_root", "version", "record_digest"}
    if set(report) != required or any(not isinstance(value, str) or not value for value in report.values()):
        msg = "Incomplete isolated helper origin report"
        raise ValueError(msg)
    if report["version"] != helper_version or report["helper_version"] != helper_version:
        msg = "Isolated helper origin report has an incompatible version"
        raise ValueError(msg)
    return report


def prepare_helper(directory: Path) -> None:
    """Create a new locked packaged helper; never upgrade an existing frozen helper."""
    directory = directory.absolute()
    if directory.resolve().is_relative_to(ROOT):
        msg = "The helper must be outside the dotfiles checkout"
        raise ValueError(msg)
    python = directory / "bin/python"
    if directory.exists() or directory.is_symlink():
        check_helper(python)
        return
    environment = {key: value for key, value in os.environ.items() if key not in SELECTORS}
    uv = shutil.which("uv")
    if uv is None:
        msg = "uv is required to prepare the isolated helper"
        raise ValueError(msg)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{directory.name}-", dir=directory.parent) as temporary:
        staged = Path(temporary) / "helper"
        environment["UV_PROJECT_ENVIRONMENT"] = str(staged)
        # Relocatable scripts keep working after the verified environment is published.
        subprocess.run(  # noqa: S603 - repository-pinned Python in a new staging directory.
            [uv, "venv", "--relocatable", "--python", (ROOT / ".python-version").read_text().strip(), str(staged)], check=True, env=environment, timeout=600
        )
        subprocess.run(  # noqa: S603 - supported locked sync into the staged environment.
            [uv, "sync", "--locked", "--project", str(ROOT), "--only-group", "tooling", "--no-default-groups", "--link-mode", "copy"],
            check=True,
            env=environment,
            timeout=600,
        )
        check_helper(staged / "bin/python")
        if directory.exists() or directory.is_symlink():
            raise FileExistsError(f"Helper destination appeared during setup: {directory}; preserve it and retry")
        staged.rename(directory)


def main(argv: list[str] | None = None) -> int:
    """Keep installation, helper preparation, and read-only checking explicit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("install", "check", "helper-setup"))
    parser.add_argument("--destination", type=Path, default=Path.home() / ".agents/skills")
    parser.add_argument("--helper", type=Path, help="override the default versioned helper directory")
    args = parser.parse_args(argv)
    try:
        if sys.platform not in {"darwin", "linux"}:
            msg = "Skills setup supports macOS and Linux; other platforms are unverified"
            raise ValueError(msg)
        helper = args.helper if args.helper is not None else default_helper_directory()
        if args.mode == "helper-setup":
            prepare_helper(helper)
            return 0
        # Check runtime and metadata before adding any discovery links.
        check_helper(helper.absolute() / "bin/python")
        for source in skill_sources(SKILLS):
            valid, diagnostic = validate_skill(source)
            if not valid:
                raise ValueError(f"Invalid skill {source.name}: {diagnostic}")
        destination = args.destination.absolute()
        if args.mode == "install":
            link_skills(SKILLS, destination)
        installed = inspect_links(SKILLS, destination, installed=True)
        print(f"Verified {len(installed)} skill directory links, metadata, and isolated helper at {destination}.")
        print("Start a new agent session to verify discovery. This command does not verify an agent's loaded skill catalog.")
        return 0
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        print(f"skills: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
