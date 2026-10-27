"""One fresh-context boundary shared by dispatch, publication and compilation."""

import shlex
from functools import cache
from pathlib import Path
from typing import Any

from review_graph_globs import path_globs_intersect
from review_graph_reads import path_only_inventory

_READ_COMMANDS = frozenset({"cat", "head", "tail", "wc", "ls", "nl", "bat", "less", "more", "rg", "grep", "sed", "awk", "jq", "find"})
_VALUE_OPTIONS = frozenset({"-g", "--glob", "--iglob", "-t", "--type", "-T", "--type-not", "-A", "-B", "-C", "-m", "--max-count", "--encoding"})
_PATTERN_OPTIONS = frozenset({"-e", "--regexp", "--expression"})
_FILE_OPTIONS = frozenset({"-f", "--file"})

ISOLATION_INSTRUCTIONS = (
    "Fresh audit isolation: do not read another node's inputs, payloads, reports, or evidence, including validator/CI evidence. "
    "Keep validator evidence delegated through planned-validation IDs and requirement-bound caveats. "
    "You may read your own dispatch/schema/publication contract, raw source, supplied shared source packets, and the exact inherited "
    "coverage references explicitly dispatched to this node. Predecessor IDs do not grant access to other evidence. "
    "Standalone rg --files and nonrecursive ls may locate paths, but filenames are neither source inspection nor evidence. "
    "Record every actual read and command; an isolation failure requires a new clean worker for this node only."
)


def forbidden_artifacts(node_id: str, entries: dict[str, dict[str, Any]]) -> list[str]:
    """Bind all other node artifacts, including compact execution views."""
    forbidden: set[str] = set()
    for other_id, entry in entries.items():
        if other_id != node_id:
            # Node-addressed sidecars include sealed payloads, coverage proofs,
            # timing receipts and failed attempts created after materialization.
            for field in (
                "artifact_path",
                "metadata_path",
                "worker_input_path",
                "worker_execution_path",
                "worker_payload_candidate_path",
                "worker_payload_contract_path",
                "worker_payload_path",
            ):
                value = entry.get(field)
                if isinstance(value, str) and value:
                    path = Path(value)
                    forbidden.update((str(path), str(path.parent / (other_id + ".*"))))
    return sorted(forbidden)


def isolation_violations(dispatch: dict[str, Any], payload: dict[str, Any]) -> tuple[str, ...]:
    """Apply the compiler's artifact boundary to truthful command and read ledgers."""
    if dispatch.get("fresh_context") is not True or dispatch.get("mode") not in {"audit", "independent-review"}:
        return ()
    root = Path(dispatch.get("repository_root", Path.cwd()))
    artifacts = _artifact_selectors(dispatch.get("fresh_context_forbidden_artifacts", []))

    @cache
    def selector(path: str) -> str:
        # Resolve each operand once per check, never across filesystem observations.
        selected = Path(path)
        return ((selected if selected.is_absolute() else root / selected).resolve() / "**").as_posix()

    violations = []
    for read in (*payload.get("files_inspected", []), *payload.get("nearby_contract_owners", [])):
        violations.extend(f"{read} -> {path}" for path in artifacts if path_globs_intersect(selector(read), selector(path)))
    for command in payload.get("commands_executed", []):
        if path_only_inventory(command):
            continue
        operands = _command_operands(command, root)
        violations.extend(
            f"{command} -> {path}"
            for path in artifacts
            if (not any(char in path for char in "*?[") and path in command)
            or any(path_globs_intersect(selector(operand), selector(path)) for operand in operands)
        )
    return tuple(violations)


def _artifact_selectors(paths: list[str]) -> set[str]:
    """Retain directory identity, including legacy basename/sidecar bindings."""
    absolute = {path for path in paths if Path(path).is_absolute()}
    result = set(absolute)
    for path in paths:
        if Path(path).is_absolute():
            continue
        matches = [item for item in absolute if Path(item).name.startswith(path) if path.endswith(".") or Path(item).name == path]
        if path.endswith("."):
            result.update(str(Path(item).parent / (path + "*")) for item in matches)
        elif not matches:
            result.add(path)  # Saved contracts with only relative bindings.
    return result


def _read_operands(words: list[str]) -> list[str]:
    """Recognize ordinary reader operands, excluding patterns and option values."""
    if not words or Path(words[0]).name not in _READ_COMMANDS:
        return []
    name = Path(words[0]).name
    pattern = name in {"rg", "grep", "sed", "awk", "jq"} and "--files" not in words
    operands: list[str] = []
    pending_file: bool | None = None
    options = True
    for word in words[1:]:
        if pending_file is not None:
            operands.extend([word] if pending_file else [])
            pending_file = None
        elif options and word == "--":
            options = False
        elif options and word in _PATTERN_OPTIONS | _FILE_OPTIONS | _VALUE_OPTIONS:
            pattern = pattern and word not in _PATTERN_OPTIONS | _FILE_OPTIONS
            pending_file = word in _FILE_OPTIONS
        elif options and word.startswith("-"):
            if word.startswith(("--regexp=", "--expression=")) or (word.startswith("-e") and len(word) > 2):
                pattern = False
        elif pattern:
            pattern = False
        else:
            operands.append(word)
    return operands or (["."] if name in {"rg", "ls", "find"} else [])


def _segment_operands(words: list[str], directory: Path) -> tuple[list[str], Path]:
    """Track explicit directory changes without treating chdir itself as a read."""
    if len(words) == 2 and words[0] == "cd" and words[1] != "-":
        return [], (directory / words[1]).resolve()
    return [str((directory / operand).resolve()) for operand in _read_operands(words)], directory


def _command_operands(command: str, directory: Path) -> list[str]:
    """Inspect shell reader commands without interpreting embedded program text."""
    # A heredoc body belongs to its program, not to the surrounding shell.
    # Literal peer paths in arbitrary programs are still checked by the caller;
    # actual reads must also be declared in the structured provenance fields.
    lines = command.replace("\\\n", "").splitlines()
    pending: list[tuple[str, bool]] = []
    operands = []
    for line in lines:
        if pending:
            delimiter, strip_tabs = pending[0]
            if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                pending.pop(0)
            continue
        words = _shell_words(line)
        segment: list[str] = []
        index = 0
        while index < len(words):
            word = words[index]
            if word in {"<<", "<<-"} and index + 1 < len(words):
                delimiter = words[index + 1]
                strip_tabs = word == "<<-" or delimiter.startswith("-")
                pending.append((delimiter.removeprefix("-") if strip_tabs else delimiter, strip_tabs))
                index += 2
                continue
            if word in {";", "&&", "||", "|", "&"}:
                selected, directory = _segment_operands(segment, directory)
                operands.extend(selected)
                segment = []
            else:
                segment.append(word)
            index += 1
        selected, directory = _segment_operands(segment, directory)
        operands.extend(selected)
    return operands


def _shell_words(line: str) -> list[str]:
    try:
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""  # Never hide later commands behind an in-word hash.
        return list(lexer)
    except ValueError:
        return []  # Structured read provenance remains authoritative for opaque syntax.


class IsolationViolationError(ValueError):
    """A truthful ledger makes the fresh worker ineligible for acceptance."""


class IsolationPublicationError(ValueError):
    """A retained rejection with bounded node-local recovery instructions."""

    def __init__(self, receipt: dict[str, Any]) -> None:
        """Preserve the exact recovery receipt for CLI and library callers."""
        self.receipt = receipt
        super().__init__(receipt["message"])
