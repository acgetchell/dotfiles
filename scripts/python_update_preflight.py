"""Select a Python update path that preserves project resolver overrides."""

import sys
import tomllib
from pathlib import Path


def main() -> int:
    """Use project resolution when the shared direct-pin updater loses overrides."""
    try:
        project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        overrides = project.get("tool", {}).get("uv", {}).get("override-dependencies")
    except (OSError, ValueError) as error:
        print(f"python-update-preflight: {error}", file=sys.stderr)
        return 1
    print("project" if overrides else "shared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
