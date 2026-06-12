"""Inspect, lint, and optionally execute Jupyter notebooks."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
import os
import sys
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Notebook lint diagnostic."""

    severity: str
    cell: int
    message: str


def cell_source(cell: dict[str, Any]) -> str:
    """Return a notebook cell source as text."""
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    if isinstance(source, str):
        return source
    msg = f"cell source must be a string or list of strings, got {type(source).__name__}"
    raise TypeError(msg)


def load_notebook(path: Path) -> dict[str, Any]:
    """Load a notebook as plain JSON."""
    if not path.is_file():
        msg = f"notebook does not exist or is not a file: {path}"
        raise FileNotFoundError(msg)
    with path.open(encoding="utf-8") as handle:
        notebook = json.load(handle)
    if notebook.get("nbformat") != 4:
        msg = f"{path}: expected nbformat 4, got {notebook.get('nbformat')!r}"
        raise ValueError(msg)
    return notebook


def code_cells(notebook: dict[str, Any]) -> list[tuple[int, dict[str, Any], str]]:
    """Return code cells with one-based cell numbers and joined source."""
    cells = []
    for index, cell in enumerate(notebook.get("cells", []), start=1):
        if cell.get("cell_type") == "code":
            cells.append((index, cell, cell_source(cell)))
    return cells


def summarize(path: Path) -> None:
    """Print a compact notebook inventory."""
    notebook = load_notebook(path)
    print(f"{path}")
    print(f"  nbformat: {notebook.get('nbformat')}.{notebook.get('nbformat_minor')}")
    for index, cell in enumerate(notebook.get("cells", []), start=1):
        source = cell_source(cell)
        first_line = next((line.strip() for line in source.splitlines() if line.strip()), "")
        outputs = len(cell.get("outputs", [])) if cell.get("cell_type") == "code" else 0
        execution_count = cell.get("execution_count") if cell.get("cell_type") == "code" else ""
        print(
            f"  cell {index:03d} {cell.get('cell_type', 'unknown'):<8} "
            f"lines={len(source.splitlines()):<3} outputs={outputs:<2} exec={execution_count!s:<4} {first_line[:100]}"
        )


class NotebookVisitor(ast.NodeVisitor):
    """Collect notebook-specific Python quality diagnostics."""

    def __init__(self, cell: int) -> None:
        self.cell = cell
        self.diagnostics: list[Diagnostic] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "pandas":
                self.diagnostics.append(
                    Diagnostic("warning", self.cell, "imports pandas; prefer Polars unless pandas is required")
                )
            if alias.name == "csv":
                self.diagnostics.append(
                    Diagnostic("warning", self.cell, "imports csv; prefer Polars for dataframe-shaped CSV analysis")
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "pandas":
            self.diagnostics.append(
                Diagnostic("warning", self.cell, "imports pandas; prefer Polars unless pandas is required")
            )
        if node.module == "csv":
            self.diagnostics.append(
                Diagnostic("warning", self.cell, "imports csv; prefer Polars for dataframe-shaped CSV analysis")
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function_annotations(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function_annotations(node)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.diagnostics.append(Diagnostic("warning", self.cell, "uses bare except; catch specific exceptions"))
        elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
            self.diagnostics.append(
                Diagnostic("warning", self.cell, f"catches broad {node.type.id}; catch specific recoverable errors")
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = dotted_name(node.func)
        if call_name in {"subprocess.run", "subprocess.Popen"}:
            if keyword_bool(node, "shell"):
                self.diagnostics.append(Diagnostic("error", self.cell, f"{call_name} uses shell=True"))
            if call_name == "subprocess.run" and not has_keyword(node, "timeout"):
                self.diagnostics.append(
                    Diagnostic("warning", self.cell, "subprocess.run lacks timeout; add one or document why it can run unbounded")
                )
            if call_name == "subprocess.Popen" and not has_wait_timeout(node):
                self.diagnostics.append(
                    Diagnostic("warning", self.cell, "subprocess.Popen stream lacks timeout; ensure tutorial commands cannot hang indefinitely")
                )
        self.generic_visit(node)

    def _check_function_annotations(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        missing_args = [
            argument.arg
            for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if argument.arg not in {"self", "cls"} and argument.annotation is None
        ]
        if node.args.vararg is not None and node.args.vararg.annotation is None:
            missing_args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg is not None and node.args.kwarg.annotation is None:
            missing_args.append(f"**{node.args.kwarg.arg}")
        if missing_args:
            self.diagnostics.append(
                Diagnostic("warning", self.cell, f"function {node.name} lacks parameter annotations: {', '.join(missing_args)}")
            )
        if node.returns is None:
            self.diagnostics.append(Diagnostic("warning", self.cell, f"function {node.name} lacks return annotation"))


def dotted_name(node: ast.AST) -> str:
    """Return a dotted expression name when statically knowable."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def has_keyword(node: ast.Call, name: str) -> bool:
    """Return whether a call has a named keyword argument."""
    return any(keyword.arg == name for keyword in node.keywords)


def keyword_bool(node: ast.Call, name: str) -> bool:
    """Return a boolean keyword value when it is statically true."""
    for keyword in node.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return keyword.value.value is True
    return False


def has_wait_timeout(node: ast.Call) -> bool:
    """Return whether a Popen call obviously wraps a timeout in the same call.

    Popen streaming patterns usually call wait() later, so this conservative
    helper currently reports false and keeps the diagnostic advisory.
    """
    return has_keyword(node, "timeout")


def lint(path: Path, *, allow_outputs: bool = False, strict: bool = False) -> int:
    """Validate notebook JSON and compile code cells."""
    notebook = load_notebook(path)
    diagnostics: list[Diagnostic] = []
    for index, cell, source in code_cells(notebook):
        try:
            tree = ast.parse(source, filename=f"{path}:cell-{index}")
        except SyntaxError as error:
            diagnostics.append(Diagnostic("error", index, f"syntax error: {error}"))
            continue
        visitor = NotebookVisitor(index)
        visitor.visit(tree)
        diagnostics.extend(visitor.diagnostics)
        outputs = cell.get("outputs", [])
        if outputs and not allow_outputs:
            diagnostics.append(Diagnostic("error", index, f"has {len(outputs)} output block(s); clear outputs before committing"))
        if cell.get("execution_count") is not None and not allow_outputs:
            diagnostics.append(Diagnostic("error", index, f"execution_count={cell.get('execution_count')}; clear execution counts"))

    for diagnostic in diagnostics:
        stream = sys.stderr if diagnostic.severity == "error" else sys.stdout
        print(f"{path}: cell {diagnostic.cell}: {diagnostic.severity}: {diagnostic.message}", file=stream)

    if any(diagnostic.severity == "error" for diagnostic in diagnostics):
        return 1
    if strict and diagnostics:
        return 1
    return 0


def execute(path: Path, repo_root: Path, timeout: int) -> None:
    """Execute a notebook in memory without modifying it on disk."""
    import nbclient
    import nbformat

    os.environ.setdefault("MPLBACKEND", "Agg")
    with path.open(encoding="utf-8") as handle:
        notebook = nbformat.read(handle, as_version=4)
    client = nbclient.NotebookClient(
        notebook,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    )
    client.execute()
    print(f"OK executed {path}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--summary", action="store_true", help="print a compact cell inventory")
    mode.add_argument("--lint", action="store_true", help="validate JSON, compile code cells, and report common notebook issues")
    mode.add_argument("--execute", action="store_true", help="execute the notebook in memory")
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--allow-outputs", action="store_true", help="do not fail lint when code cells contain outputs or execution counts")
    parser.add_argument("--strict", action="store_true", help="treat warning diagnostics as lint failures")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="working directory for execution")
    parser.add_argument("--timeout", type=int, default=120, help="per-cell execution timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the requested notebook check."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.summary:
        summarize(args.notebook)
        return 0
    if args.lint:
        return lint(args.notebook, allow_outputs=args.allow_outputs, strict=args.strict)
    execute(args.notebook, args.repo_root, args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
