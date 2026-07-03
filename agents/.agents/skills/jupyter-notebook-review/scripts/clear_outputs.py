"""Clear outputs and execution counts from Jupyter notebooks."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import nbformat


def clear_outputs(path: Path) -> None:
    """Clear code-cell outputs and execution counts in place."""
    with path.open(encoding="utf-8") as handle:
        notebook = nbformat.read(handle, as_version=4)

    for cell in notebook.cells:
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
        temp_path = Path(handle.name)
        nbformat.write(notebook, handle)
    temp_path.replace(path)
    print(f"Cleared outputs in {path}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebooks", nargs="+", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Clear every requested notebook."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    for path in args.notebooks:
        clear_outputs(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
