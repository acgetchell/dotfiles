"""Inspect notebooks and report skill-specific review advice.

Shared validation, lint, cleanup, and execution belong to research-repo-tools.
Retire this remaining inspection/advice helper through dotfiles issue #78 after
research-repo-tools v0.1.5 supplies the capabilities in upstream issues #39/#40.
"""

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast, override

GENERATED_CELL_ID_RE = re.compile(
    r"^(?:(?i:[a-f0-9]{8}|[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12})|"
    r"(?:cell|code|markdown|raw|section|step)-?[0-9]+)$"
)


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
        if not all(isinstance(part, str) for part in source):
            msg = "cell source list items must all be strings"
            raise TypeError(msg)
        return "".join(cast("list[str]", source))
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
        loaded: object = json.load(handle)
    if not isinstance(loaded, dict):
        msg = f"{path}: notebook root must be a JSON object, got {type(loaded).__name__}"
        raise TypeError(msg)
    notebook = cast("dict[str, Any]", loaded)
    notebook_metadata = notebook.get("metadata")
    if not isinstance(notebook_metadata, dict):
        msg = f"{path}: metadata must be a JSON object, got {type(notebook_metadata).__name__}"
        raise TypeError(msg)
    nbformat = notebook.get("nbformat")
    if isinstance(nbformat, bool) or not isinstance(nbformat, int) or nbformat != 4:
        msg = f"{path}: expected nbformat to be the JSON integer 4, got {nbformat!r}"
        raise ValueError(msg)
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        msg = f"{path}: cells must be a JSON array, got {type(cells).__name__}"
        raise TypeError(msg)
    for index, cell in enumerate(cells, start=1):
        if not isinstance(cell, dict):
            msg = f"{path}: cell {index} must be a JSON object, got {type(cell).__name__}"
            raise TypeError(msg)
        metadata = cell.get("metadata")
        if not isinstance(metadata, dict):
            msg = f"{path}: cell {index} metadata must be a JSON object, got {type(metadata).__name__}"
            raise TypeError(msg)
        try:
            cell_source(cell)
        except TypeError as error:
            msg = f"{path}: cell {index} {error}"
            raise TypeError(msg) from error
    return notebook


def code_cells(notebook: dict[str, Any]) -> list[tuple[int, dict[str, Any], str]]:
    """Return code cells with one-based cell numbers and joined source."""
    cells = []
    for index, cell in enumerate(notebook.get("cells", []), start=1):
        if cell.get("cell_type") == "code":
            cells.append((index, cell, cell_source(cell)))
    return cells


def cell_id_advice(notebook: dict[str, Any]) -> list[Diagnostic]:
    """Suggest descriptive IDs; structural ID validation is owned upstream."""
    return [
        Diagnostic("warning", index, f"cell id {cell_id!r} looks generated or positional; name the cell's purpose")
        for index, cell in enumerate(notebook["cells"], start=1)
        if isinstance(cell_id := cell.get("id"), str) and GENERATED_CELL_ID_RE.fullmatch(cell_id) is not None
    ]


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
        cell_id = cell.get("id", "<missing>")
        print(
            f"  cell {index:03d} {cell.get('cell_type', 'unknown'):<8} id={cell_id!s:<24} "
            f"lines={len(source.splitlines()):<3} outputs={outputs:<2} exec={execution_count!s:<4} {first_line[:100]}"
        )


class NotebookVisitor(ast.NodeVisitor):
    """Collect notebook-specific Python quality diagnostics."""

    def __init__(self, cell: int) -> None:
        """Create a visitor that reports diagnostics against one notebook cell."""
        self.cell = cell
        self.diagnostics: list[Diagnostic] = []

    @override
    def visit_Import(self, node: ast.Import) -> None:
        """Flag imports that conflict with notebook style guidance."""
        for alias in node.names:
            if alias.name == "pandas":
                self.diagnostics.append(Diagnostic("warning", self.cell, "imports pandas; prefer Polars unless pandas is required"))
            if alias.name == "csv":
                self.diagnostics.append(Diagnostic("warning", self.cell, "imports csv; prefer Polars for dataframe-shaped CSV analysis"))
        self.generic_visit(node)

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Flag from-imports that conflict with notebook style guidance."""
        if node.module == "pandas":
            self.diagnostics.append(Diagnostic("warning", self.cell, "imports pandas; prefer Polars unless pandas is required"))
        if node.module == "csv":
            self.diagnostics.append(Diagnostic("warning", self.cell, "imports csv; prefer Polars for dataframe-shaped CSV analysis"))
        self.generic_visit(node)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check synchronous function annotations."""
        self._check_function_annotations(node)
        self.generic_visit(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check asynchronous function annotations."""
        self._check_function_annotations(node)
        self.generic_visit(node)

    @override
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Flag broad exception handlers in notebook code."""
        if node.type is None:
            self.diagnostics.append(Diagnostic("warning", self.cell, "uses bare except; catch specific exceptions"))
        elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
            self.diagnostics.append(Diagnostic("warning", self.cell, f"catches broad {node.type.id}; catch specific recoverable errors"))
        self.generic_visit(node)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        """Flag risky subprocess calls in notebook code."""
        call_name = dotted_name(node.func)
        if call_name in {"subprocess.run", "subprocess.Popen"}:
            if keyword_bool(node, "shell"):
                self.diagnostics.append(Diagnostic("error", self.cell, f"{call_name} uses shell=True"))
            if call_name == "subprocess.run" and not has_keyword(node, "timeout"):
                self.diagnostics.append(Diagnostic("warning", self.cell, "subprocess.run lacks timeout; add one or document why it can run unbounded"))
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
            self.diagnostics.append(Diagnostic("warning", self.cell, f"function {node.name} lacks parameter annotations: {', '.join(missing_args)}"))
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


def code_cell_advice(path: Path, notebook: dict[str, Any]) -> list[Diagnostic]:
    """Apply plain-Python review heuristics without competing with native lint."""
    diagnostics: list[Diagnostic] = []
    for index, _cell, source in code_cells(notebook):
        try:
            tree = ast.parse(source, filename=f"{path}:cell-{index}")
        except SyntaxError:
            diagnostics.append(Diagnostic("info", index, "plain-Python advice skipped; use shared notebook lint for syntax and IPython magics"))
            continue
        visitor = NotebookVisitor(index)
        visitor.visit(tree)
        diagnostics.extend(visitor.diagnostics)
    return diagnostics


def advise(path: Path, *, strict: bool = False) -> int:
    """Report the skill's additional review policy without linting or executing."""
    notebook = load_notebook(path)
    diagnostics = [*cell_id_advice(notebook), *code_cell_advice(path, notebook)]
    for diagnostic in diagnostics:
        stream = sys.stderr if diagnostic.severity == "error" else sys.stdout
        print(f"{path}: cell {diagnostic.cell}: {diagnostic.severity}: {diagnostic.message}", file=stream)
    return int(any(item.severity == "error" or (strict and item.severity == "warning") for item in diagnostics))


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse inspection and advisory arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--summary", action="store_true", help="print a compact cell inventory, including IDs awaiting repair")
    mode.add_argument("--advice", action="store_true", help="report skill-specific review advice; run shared notebook lint separately")
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--strict", action="store_true", help="treat advisory warnings as failures")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the requested inspection or advisory pass."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.summary:
            summarize(args.notebook)
            return 0
        return advise(args.notebook, strict=args.strict)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"notebook_check: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
