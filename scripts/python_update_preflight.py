"""Reject automated pin updates that cannot preserve project resolver overrides."""

import sys
import tomllib
from pathlib import Path


def main() -> int:
    """Fail before the shared updater can change the manifest or lockfile."""
    try:
        project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        if project.get("tool", {}).get("uv", {}).get("override-dependencies"):
            msg = (
                "Python pin update blocked: research-repo-tools 0.1.9's isolated resolver does not preserve project override-dependencies. "
                "Use uv lock --upgrade for a project-aware transitive refresh; update exact direct pins deliberately and review the diff. "
                "Remove this guard only after the shared updater preserves overrides."
            )
            raise ValueError(msg)
    except (OSError, ValueError) as error:
        print(f"python-update-preflight: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
