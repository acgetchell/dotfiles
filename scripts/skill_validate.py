#!/usr/bin/env python3
"""Validate Codex skill metadata stored in this repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

if TYPE_CHECKING:
    from collections.abc import Sequence

UTF8 = "utf-8"
MAX_SKILL_NAME_LENGTH = 64
ALLOWED_FRONTMATTER_KEYS = frozenset({"name", "description", "license", "allowed-tools", "metadata"})
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
SKILL_NAME_RE = re.compile(r"^[a-z0-9-]+$")


def load_frontmatter(skill_path: Path | str) -> tuple[dict[str, object] | None, str]:
    """Load validated YAML frontmatter from one skill directory."""
    frontmatter_text, message = read_frontmatter_text(skill_path)
    if frontmatter_text is None:
        return None, message

    return parse_frontmatter(frontmatter_text)


def read_frontmatter_text(skill_path: Path | str) -> tuple[str | None, str]:
    """Read the raw frontmatter block from a skill directory."""
    skill_md = Path(skill_path) / "SKILL.md"
    if not skill_md.exists():
        return None, "SKILL.md not found"

    content = skill_md.read_text(encoding=UTF8)
    if not content.startswith("---"):
        return None, "No YAML frontmatter found"

    match = FRONTMATTER_RE.match(content)
    if match is None:
        return None, "Invalid frontmatter format"
    return match.group(1), ""


def parse_frontmatter(frontmatter_text: str) -> tuple[dict[str, object] | None, str]:
    """Parse and validate the raw YAML frontmatter shape."""
    try:
        loaded_frontmatter: Any = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        return None, f"Invalid YAML in frontmatter: {exc}"

    if not isinstance(loaded_frontmatter, dict):
        return None, "Frontmatter must be a YAML dictionary"

    frontmatter = cast("dict[object, object]", loaded_frontmatter)
    non_string_keys = [key for key in frontmatter if not isinstance(key, str)]
    if non_string_keys:
        keys = ", ".join(repr(key) for key in non_string_keys)
        return None, f"Frontmatter keys must be strings: {keys}"

    return cast("dict[str, object]", frontmatter), ""


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
    """Validate one skill directory."""
    frontmatter, message = load_frontmatter(skill_path)
    if frontmatter is None:
        return False, message
    return validate_frontmatter(frontmatter)


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
    parser.add_argument("skill", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run skill validation."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        valid, message = validate_skill(args.skill)
    except (OSError, UnicodeError) as exc:
        print(f"failed to validate skill: {exc}", file=sys.stderr)
        return 1

    output = sys.stdout if valid else sys.stderr
    print(message, file=output)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
