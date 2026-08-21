#!/usr/bin/env python3
"""Verify stow symlink integrity for this dotfiles repository.

Checks that stowed files resolve to existing files inside the dotfiles
repository and flags dangling symlinks left behind by renamed or removed
packages or skills.
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

FILE_PACKAGES = ("git", "zsh")
SKILLS_SUBDIR = Path(".agents") / "skills"
CHECK_MARK = "\033[32m✓\033[0m"
CROSS_MARK = "\033[31m✗\033[0m"


@dataclass
class Report:
    """Accumulated outcomes for one check section."""

    passes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def ok(self, message: str) -> None:
        """Record a passing check."""
        self.passes.append(message)

    def fail(self, message: str) -> None:
        """Record a failing check."""
        self.failures.append(message)


def resolve_link(link: Path) -> Path:
    """Return the absolute path one symlink references, whether or not the target exists."""
    target = link.readlink()
    if not target.is_absolute():
        target = link.parent / target
    return target.resolve()


def check_stowed_file(home_file: Path, source: Path, dotfiles_dir: Path, report: Report) -> None:
    """Check that one stowed file is a symlink resolving to its expected repository source."""
    if home_file.is_symlink():
        raw_target = home_file.readlink()
        if not home_file.exists():
            report.fail(f"{home_file} is a dangling symlink -> {raw_target}")
        elif resolve_link(home_file) == source.resolve():
            report.ok(f"{home_file} -> {raw_target}")
        elif resolve_link(home_file).is_relative_to(dotfiles_dir):
            report.fail(f"{home_file} symlink points to the wrong repository file (expected {source})")
        else:
            report.fail(f"{home_file} symlink points outside {dotfiles_dir}")
    elif home_file.exists():
        report.fail(f"{home_file} exists but is not a stow symlink into {dotfiles_dir}")
    else:
        report.fail(f"{home_file} missing (run: just stow-apply-all)")


def check_package_files(home: Path, dotfiles_dir: Path) -> Report:
    """Check stowed links for every file present in the file-level packages.

    Expected links are derived from the package contents, so gitignored
    machine-local files such as zsh/.zshrc.local are only required when the
    package copy exists on this machine.
    """
    report = Report()
    for package in FILE_PACKAGES:
        package_dir = dotfiles_dir / package
        if not package_dir.is_dir():
            report.fail(f"{package_dir} missing from repository")
            continue
        for source in sorted(package_dir.iterdir()):
            if source.name == ".DS_Store":
                continue
            check_stowed_file(home / source.name, source, dotfiles_dir, report)
    return report


def check_stowed_skill_file(link: Path, source: Path, report: Report) -> bool:
    """Check one file link created by a no-folding Stow operation."""
    if not link.is_symlink():
        report.fail(f"skill file not stowed: {link} (expected {source})")
        return False
    if not link.exists():
        report.fail(f"dangling skill symlink: {link} -> {link.readlink()}")
        return False
    if resolve_link(link) != source.resolve():
        report.fail(f"skill file points to wrong target: {link} -> {link.readlink()} (expected {source})")
        return False
    return True


def check_stowed_skill(link: Path, source: Path, report: Report) -> bool:
    """Check one skill installed as a directory link or no-folding file tree."""
    if link.is_symlink():
        if not link.exists():
            report.fail(f"dangling skill symlink: {link} -> {link.readlink()}")
            return False
        if resolve_link(link) != source.resolve():
            report.fail(f"skill points to wrong target: {link} -> {link.readlink()} (expected {source})")
            return False
        return True
    if not link.is_dir():
        report.fail(f"skill not stowed: {source.name} (run: just stow-apply agents)")
        return False

    all_stowed = True
    for source_file in sorted(source.rglob("*")):
        if source_file.is_dir() and not source_file.is_symlink():
            continue
        target_file = link / source_file.relative_to(source)
        all_stowed = check_stowed_skill_file(target_file, source_file, report) and all_stowed
    return all_stowed


def check_skills(home: Path, dotfiles_dir: Path) -> Report:
    """Check per-skill symlinks under ~/.agents/skills in both directions."""
    report = Report()
    skills_dir = home / SKILLS_SUBDIR
    repo_skills_dir = dotfiles_dir / "agents" / SKILLS_SUBDIR
    if not skills_dir.is_dir():
        report.fail(f"{skills_dir} missing (run: just stow-apply agents)")
        return report
    if not repo_skills_dir.is_dir():
        report.fail(f"{repo_skills_dir} missing from repository")
        return report

    dangling = [link for link in sorted(skills_dir.rglob("*")) if link.is_symlink() and not link.exists() and resolve_link(link).is_relative_to(dotfiles_dir)]
    for link in dangling:
        report.fail(f"dangling skill symlink: {link} -> {link.readlink()}")
    if not dangling:
        report.ok(f"no dangling symlinks in {skills_dir}")

    all_stowed = True
    for entry in sorted(repo_skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        all_stowed = check_stowed_skill(skills_dir / entry.name, entry, report) and all_stowed

    if all_stowed:
        report.ok(f"all repo skills reachable from {skills_dir}")
    return report


def check_home_links(home: Path, dotfiles_dir: Path) -> Report:
    """Flag dangling top-level home symlinks that point into the repository."""
    report = Report()
    if not home.is_dir():
        report.fail(f"{home} missing or is not a directory")
        return report
    stale = [entry for entry in sorted(home.iterdir()) if entry.is_symlink() and not entry.exists() and resolve_link(entry).is_relative_to(dotfiles_dir)]
    for link in stale:
        report.fail(f"dangling symlink: {link} -> {link.readlink()}")
    if not stale:
        report.ok(f"no dangling top-level symlinks into {dotfiles_dir}")
    return report


def print_report(title: str, report: Report) -> None:
    """Print one section's outcomes in bin/verify.sh style."""
    print(f"==> {title}")
    for message in report.passes:
        print(f"  {CHECK_MARK} {message}")
    for message in report.failures:
        print(f"  {CROSS_MARK} {message}")


def default_dotfiles_dir() -> Path:
    """Return the dotfiles directory from DOTFILES_DIR or the standard location."""
    env_value = os.environ.get("DOTFILES_DIR")
    if env_value:
        return Path(env_value)
    return Path.home() / "projects" / "dotfiles"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__, suggest_on_error=True, color=False)
    parser.add_argument(
        "--dotfiles-dir", type=Path, default=default_dotfiles_dir(), help="dotfiles repository root (default: $DOTFILES_DIR or ~/projects/dotfiles)"
    )
    parser.add_argument("--home", type=Path, default=Path.home(), help="home directory to inspect (default: current user home)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run all stow symlink checks and report failures."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    home = args.home.resolve()
    dotfiles_dir = args.dotfiles_dir.resolve()

    sections = (
        ("Stowed files", check_package_files(home, dotfiles_dir)),
        ("Skill symlinks", check_skills(home, dotfiles_dir)),
        ("Top-level $HOME symlinks", check_home_links(home, dotfiles_dir)),
    )
    failed = False
    for title, report in sections:
        print_report(title, report)
        failed = failed or bool(report.failures)

    if failed:
        print("==> stow_verify: FAILURES detected", file=sys.stderr)
        return 1
    print("==> stow_verify: all stow symlinks verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
