#!/usr/bin/env python3
"""Validate Codex skill metadata stored in this repository."""

__lazy_modules__ = ("argparse", "subprocess", "research_repo_tools.process", "research_repo_tools.selection")

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import yaml
from research_repo_tools.process import ExecutableNotFoundError
from research_repo_tools.selection import select_files

# The shared YAML reader ships with the standalone and frozen graph runtimes.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents/.agents/skills/review-graph/scripts"))
import review_graph_frontmatter as frontmatter_yaml

if TYPE_CHECKING:
    from collections.abc import Sequence

UTF8 = "utf-8"
MAX_SKILL_NAME_LENGTH = 64
MIN_SHORT_DESCRIPTION_LENGTH = 25
MAX_SHORT_DESCRIPTION_LENGTH = 64
ALLOWED_FRONTMATTER_KEYS = frozenset({"name", "description", "license", "allowed-tools", "metadata"})
SKILL_NAME_RE = re.compile(r"^[a-z0-9-]+$")


parse_frontmatter = frontmatter_yaml.parse_frontmatter


def load_frontmatter(skill_path: Path | str) -> tuple[dict[str, object] | None, str]:
    """Read SKILL.md and return its parsed mapping or (None, diagnostic).

    A mapping has an empty diagnostic and still needs field validation.
    File read and decoding errors propagate to the caller.
    """
    frontmatter_text, message = read_frontmatter_text(skill_path)
    if frontmatter_text is None:
        return None, message

    return parse_frontmatter(frontmatter_text)


def read_frontmatter_text(skill_path: Path | str) -> tuple[str | None, str]:
    """Read the raw frontmatter block from a skill directory."""
    skill_md = Path(skill_path) / "SKILL.md"
    if not skill_md.exists():
        return None, "SKILL.md not found"

    return frontmatter_yaml.frontmatter_text(skill_md.read_text(encoding=UTF8))


def validate_frontmatter(frontmatter: dict[str, object]) -> tuple[bool, str]:
    """Validate supported skill frontmatter fields."""
    unexpected_keys = set(frontmatter) - ALLOWED_FRONTMATTER_KEYS
    if unexpected_keys:
        allowed = ", ".join(sorted(ALLOWED_FRONTMATTER_KEYS))
        unexpected = ", ".join(sorted(unexpected_keys))
        return False, f"Unexpected key(s) in SKILL.md frontmatter: {unexpected}. Allowed properties are: {allowed}"

    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    valid_name, name_message = validate_name(frontmatter["name"])
    if not valid_name:
        return False, name_message

    valid_description, description_message = validate_description(frontmatter["description"])
    if not valid_description:
        return False, description_message

    return True, "Skill is valid!"


def validate_skill(skill_path: Path | str) -> tuple[bool, str]:
    """Check SKILL.md and agents/openai.yaml, returning success or the first diagnostic.

    The boolean indicates validity. The message is suitable for display in either case.
    File read and decoding errors propagate to the caller.
    """
    skill_dir = Path(skill_path)
    frontmatter, message = load_frontmatter(skill_dir)
    if frontmatter is None:
        return False, message

    valid_frontmatter, frontmatter_message = validate_frontmatter(frontmatter)
    if not valid_frontmatter:
        return False, frontmatter_message

    skill_name = cast("str", frontmatter["name"])
    if skill_name != skill_dir.name:
        return False, f"Frontmatter name '{skill_name}' must match skill directory '{skill_dir.name}'"

    openai_metadata, metadata_message = load_openai_metadata(skill_dir)
    if openai_metadata is None:
        return False, metadata_message

    return validate_openai_metadata(openai_metadata, skill_name)


def load_openai_metadata(skill_path: Path | str) -> tuple[dict[str, object] | None, str]:
    """Load product UI metadata from one skill directory."""
    metadata_path = Path(skill_path) / "agents" / "openai.yaml"
    if not metadata_path.exists():
        return None, "agents/openai.yaml not found"

    try:
        loaded_metadata = frontmatter_yaml.load_safe_yaml(metadata_path.read_text(encoding=UTF8))
    except (yaml.YAMLError, ValueError) as exc:
        return None, f"Invalid YAML in agents/openai.yaml: {exc}"

    return frontmatter_yaml.string_keyed_mapping(loaded_metadata, "agents/openai.yaml")


def validate_openai_metadata(metadata: dict[str, object], skill_name: str) -> tuple[bool, str]:
    """Validate required user-facing skill metadata."""
    loaded_interface = metadata.get("interface")
    if not isinstance(loaded_interface, dict):
        return False, "agents/openai.yaml must contain an 'interface' dictionary"
    interface = cast("dict[str, object]", loaded_interface)

    for field in ("display_name", "short_description", "default_prompt"):
        value = interface.get(field)
        if not isinstance(value, str) or not value.strip():
            return False, f"interface.{field} must be a non-empty string"

    short_description = cast("str", interface["short_description"]).strip()
    if not MIN_SHORT_DESCRIPTION_LENGTH <= len(short_description) <= MAX_SHORT_DESCRIPTION_LENGTH:
        return False, (f"interface.short_description must be {MIN_SHORT_DESCRIPTION_LENGTH}-{MAX_SHORT_DESCRIPTION_LENGTH} characters")

    default_prompt = cast("str", interface["default_prompt"])
    invocation = f"${skill_name}"
    if re.search(rf"{re.escape(invocation)}(?![a-z0-9-])", default_prompt) is None:
        return False, f"interface.default_prompt must mention {invocation}"

    return True, "Skill is valid!"


def validate_name(name_value: object) -> tuple[bool, str]:
    """Validate a skill name value from frontmatter."""
    if not isinstance(name_value, str):
        return False, f"Name must be a string, got {type(name_value).__name__}"

    name = name_value.strip()
    if not name:
        return False, "Name cannot be empty"
    if not SKILL_NAME_RE.match(name):
        return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)"
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
    if len(name) > MAX_SKILL_NAME_LENGTH:
        return False, f"Name is too long ({len(name)} characters). Maximum is {MAX_SKILL_NAME_LENGTH} characters."
    return True, ""


def validate_description(description_value: object) -> tuple[bool, str]:
    """Validate a skill description value from frontmatter."""
    if not isinstance(description_value, str):
        return False, f"Description must be a string, got {type(description_value).__name__}"

    description = description_value.strip()
    if not description:
        return False, "Description cannot be empty"
    if "<" in description or ">" in description:
        return False, "Description cannot contain angle brackets (< or >)"
    if len(description) > 1024:
        return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters."
    return True, ""


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__, suggest_on_error=True, color=False)
    parser.add_argument("skills", type=Path, nargs="*")
    parser.add_argument("--repository", type=Path, help="Validate all tracked/nonignored skill entrypoints in one process")
    args = parser.parse_args(argv)
    if bool(args.skills) == bool(args.repository):
        parser.error("supply skill directories or --repository, exclusively")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Report each selected skill and return 1 on inventory or validation failure."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    skills = args.skills
    if args.repository is not None:
        try:
            skills = [args.repository / Path(path).parent for path in select_files(args.repository, include=(":(glob)agents/.agents/skills/*/SKILL.md",))]
        except (ExecutableNotFoundError, OSError, ValueError, subprocess.SubprocessError) as exc:
            print(f"failed to inventory skills: {exc}", file=sys.stderr)
            return 1
    failed = False
    for skill in skills:
        try:
            valid, message = validate_skill(skill)
        except (OSError, UnicodeError) as exc:
            valid, message = False, f"failed to validate skill: {exc}"
        prefix = f"{skill}: " if args.repository is not None or len(skills) > 1 else ""
        print(prefix + message, file=sys.stdout if valid else sys.stderr)
        failed |= not valid
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
