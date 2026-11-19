"""Check profile tools, fresh shells, links, and helper provenance without synchronization."""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from linux_review import inventory, verify_rust_version
from skills_install import SKILLS, check_helper, default_helper_directory, inspect_links
from stow_verify import Report, check_stowed_file

ROOT = Path(__file__).resolve().parents[1]


def check_shell(shell: str, expected: dict[str, str]) -> None:
    """Resolve tools through the user's actual fresh login/interactive startup."""
    executable = shutil.which(shell)
    if executable is None:
        raise ValueError(f"Missing {shell}")
    commands = []
    for name, version in expected.items():
        commands.append(f"command -v {shlex.quote(name)} >/dev/null || exit 2")
        if version:
            commands.append(f'[ "$({shlex.quote(name)} --version | head -n 1)" = {shlex.quote(version)} ] || exit 2')
    options = "-lic" if shell in {"bash", "zsh"} else "-lc"
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(  # noqa: S603 - fixed shells and read-only version probes.
        [executable, options, "\n".join(commands)], check=False, capture_output=True, text=True, env=environment, timeout=30
    )
    if result.returncode:
        raise ValueError(f"Fresh {shell} cannot resolve the selected tools; inspect shell links, PATH, and local overrides")


def check_profile() -> dict[str, object]:
    """Return evidence for the declared profile, not full project/review acceptance."""
    report = inventory()
    invalid = [name for name, tool in report["tools"].items() if not tool["available"] or not tool["pin_matches"]]
    invalid.extend(name for name in ("python", "semgrep") if not report["scanner"][name]["pin_matches"])
    if invalid:
        raise ValueError(f"Missing or incorrectly pinned tools: {', '.join(invalid)}; rerun connected profile setup")
    verify_rust_version(report["tools"]["rustc"]["identity"])
    expected = {name: report["tools"][name]["identity"] for name in ("uv", "just", "rustc", "cargo")}
    expected.update(git="", gh="")
    for shell in ("bash", "zsh"):
        check_shell(shell, expected)
    links = Report()
    for package in ("git", "zsh", "bash"):
        for source in (ROOT / package).iterdir():
            if source.is_file() and not source.name.endswith(".local"):
                check_stowed_file(Path.home() / source.name, source, ROOT, links)
    if links.failures:
        raise ValueError("; ".join(links.failures))
    destination = Path(os.environ.get("DOTFILES_REVIEW_SKILLS_DIR", Path.home() / ".agents/skills"))
    inspect_links(SKILLS, destination, installed=True)
    origin = check_helper(default_helper_directory() / "bin/python")
    return {
        "status": "passed",
        "environment": report,
        "helper_version": origin["version"],
        "shells": ["bash", "zsh"],
        "scope": "environment readiness and skill discovery prerequisites; no agent-session discovery or project tests",
    }


def main() -> int:
    """Report one read-only health result."""
    try:
        print(json.dumps(check_profile(), sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        print(f"profile doctor: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
