"""Narrow readiness reconciliation for immutable software DOI validation reports."""

import json
import re
import shlex
from hashlib import sha256
from pathlib import Path
from typing import Any


def _reject(detail: str) -> ValueError:
    return ValueError(f"software DOI reconciliation: {detail}")


def _execution(record: dict[str, Any], index: int, result: str) -> dict[str, Any]:
    executions = record.get("executions", [])
    if type(index) is not int or not 0 <= index < len(executions):
        msg = "execution index is outside the accepted validator"
        raise _reject(msg)
    execution = executions[index]
    expected_code = "1" if result == "failed" else "0"
    if execution["result"] != result or str(execution.get("exit_code")) != expected_code:
        msg = "requires an exit-1 DOI check and an exit-0 canonical check"
        raise _reject(msg)
    return execution


def _checker_arguments(command: str) -> list[str]:
    words = shlex.split(command)
    scripts = [index for index, word in enumerate(words) if Path(word).name == "validate_reference_dois.py"]
    if len(scripts) != 1:
        msg = "execution must invoke validate_reference_dois.py"
        raise _reject(msg)
    if any(word in {";", "&&", "||", "|", ">", "2>"} for word in words[: scripts[0]]):
        msg = "compound checker commands cannot be reconciled"
        raise _reject(msg)
    args = words[scripts[0] + 1 :]
    if len(args) >= 2 and args[-2] in {">", "1>"}:
        args = args[:-2]
    return args


def _command_inputs(execution: dict[str, Any]) -> tuple[Path, Path | None]:
    args = _checker_arguments(execution["command"])
    positional: list[str] = []
    cff = None
    has_json = False
    while args:
        word = args.pop(0)
        if word == "--json":
            has_json = True
        elif word in {"--citation-cff", "--timeout", "--min-title-score"} and args:
            value = args.pop(0)
            if word == "--citation-cff":
                cff = value
        elif word.startswith("-") or word in {";", "&&", "||", "|", ">", "2>"}:
            msg = "unsupported checker command; use explicit arguments and JSON output"
            raise _reject(msg)
        else:
            positional.append(word)
    if len(positional) != 1 or not has_json:
        msg = "checker command must name exactly one Markdown input and --json"
        raise _reject(msg)
    directory = Path(execution["working_directory"])
    if not directory.is_absolute():
        msg = "checker working directory must be absolute"
        raise _reject(msg)
    return (directory / positional[0]).resolve(), (directory / cff).resolve() if cff else None


def _report(record: dict[str, Any], execution: dict[str, Any], path: str) -> dict[tuple[str, int], dict[str, Any]]:
    artifacts = [item for item in record.get("artifacts", []) if item["path"] == path]
    if path not in execution.get("artifact_paths", []) or len(artifacts) != 1:
        msg = "report is not bound to the accepted execution"
        raise _reject(msg)
    artifact = artifacts[0]
    if artifact.get("artifact_digest_mode") != "content-sha256-v1" or not Path(path).is_absolute() or Path(path).is_symlink() or not Path(path).is_file():
        msg = "report requires an absolute regular file with a content digest"
        raise _reject(msg)
    try:
        content = Path(path).read_bytes()
        if "sha256:" + sha256(content).hexdigest() != artifact["artifact_digest"]:
            msg = "report bytes changed after validation"
            raise _reject(msg)
        rows = json.loads(content)
    except (OSError, ValueError) as exc:
        raise _reject(f"cannot verify report: {exc}") from exc
    if not isinstance(rows, list) or not rows:
        msg = "report must contain DOI results"
        raise _reject(msg)
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("doi"), str) or type(row.get("line")) is not int or row["line"] < 1:
            msg = "report has an invalid DOI occurrence"
            raise _reject(msg)
        key = (row["doi"].casefold(), row["line"])
        if key in indexed:
            msg = "report repeats a DOI occurrence"
            raise _reject(msg)
        indexed[key] = row
    return indexed


def inspect_manual_doi_check(record: dict[str, Any], index: int, report_path: str) -> None:
    """Establish eligibility for a new canonical check without declaring readiness."""
    if record.get("record_type") != "validation" or record.get("status") != "failed":
        msg = "original evidence must remain a failed validator"
        raise _reject(msg)
    execution = _execution(record, index, "failed")
    _command_inputs(execution)
    rows = _report(record, execution, report_path)
    statuses = [row.get("status") for row in rows.values()]
    if any(status not in ("OK", "INSUFFICIENT_CONTEXT", "MISMATCH") for status in statuses) or all(status == "OK" for status in statuses):
        msg = "original report is not a completed DOI metadata check"
        raise _reject(msg)


def inspect_canonical_recheck(record: dict[str, Any], request: dict[str, Any], command: str, directory: str) -> None:
    """Limit source-preserving expansion to a canonical check of the same input."""
    inspect_manual_doi_check(record, request["execution_index"], request["original_report"])
    original, _cff = _command_inputs(_execution(record, request["execution_index"], "failed"))
    replacement, cff = _command_inputs({"command": command, "working_directory": directory})
    if replacement != original or cff is None:
        msg = "recheck must name the original Markdown input and --citation-cff"
        raise _reject(msg)


def _identity(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


def _canonical_match(row: dict[str, Any], cff: Path) -> None:
    canonical = row.get("canonical_software")
    if not isinstance(canonical, dict) or canonical.get("path") != str(cff):
        msg = "canonical identity does not name the executed CITATION.cff"
        raise _reject(msg)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(canonical.get("digest", ""))):
        msg = "canonical metadata has no content digest"
        raise _reject(msg)
    fields = (("doi", "doi"), ("title", "resolved_title"), ("year", "resolved_year"))
    for expected, actual in fields:
        left, right = canonical.get(expected), row.get(actual)
        if not isinstance(left, str) or not isinstance(right, str) or not _identity(left):
            raise _reject(f"canonical {expected} is missing")
        matches = left.casefold() == right.casefold() if expected == "doi" else _identity(left) == _identity(right)
        if not matches:
            raise _reject(f"canonical {expected} does not match resolved identity")
    authors, resolved = canonical.get("authors"), row.get("resolved_authors")
    if not isinstance(authors, list) or not authors or not isinstance(resolved, list) or not resolved:
        msg = "canonical or resolved authors are missing"
        raise _reject(msg)
    if any(not isinstance(name, str) or not _identity(name) for name in [*authors, *resolved]):
        msg = "invalid canonical or resolved author"
        raise _reject(msg)
    if {_identity(name) for name in authors} != {_identity(name) for name in resolved}:
        msg = "canonical authors do not match resolved identity"
        raise _reject(msg)


def _reconcile_reports(original: dict[str, Any], verified: dict[str, Any], check: dict[str, Any]) -> None:  # noqa: C901
    old_execution = _execution(original, check["execution_index"], "failed")
    new_execution = _execution(verified, check["verification_execution_index"], "passed")
    old_input, _old_cff = _command_inputs(old_execution)
    new_input, cff = _command_inputs(new_execution)
    if old_input != new_input or cff is None:
        msg = "canonical check must use the original Markdown input and explicit CITATION.cff"
        raise _reject(msg)
    old_rows = _report(original, old_execution, check["original_report"])
    new_rows = _report(verified, new_execution, check["verification_report"])
    if old_rows.keys() != new_rows.keys():
        msg = "canonical check must cover exactly the original DOI occurrences"
        raise _reject(msg)
    canonical_digest = None
    for key, old in old_rows.items():
        new = new_rows[key]
        if new.get("status") != "OK":
            msg = "canonical check has unresolved DOI results"
            raise _reject(msg)
        source = new.get("source", {})
        if not isinstance(source, dict) or source.get("path") != str(new_input) or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(source.get("digest", ""))):
            msg = "canonical report lacks a bound Markdown source"
            raise _reject(msg)
        if "source" in old and old["source"] != source:
            msg = "Markdown source changed between checks"
            raise _reject(msg)
        fields = ("resolved_title", "resolved_year", "resolved_authors", "resolved_container")
        if any(old.get(field) != new.get(field) for field in fields):
            msg = "resolved metadata changed between checks; inspect the new identity"
            raise _reject(msg)
        if old.get("status") == "OK":
            continue
        if old.get("status") not in {"INSUFFICIENT_CONTEXT", "MISMATCH"} or new.get("local_status") != "INSUFFICIENT_CONTEXT":
            msg = "contradictory local bibliographic claims cannot be reconciled"
            raise _reject(msg)
        _canonical_match(new, cff)
        digest = new["canonical_software"]["digest"]
        if canonical_digest is not None and digest != canonical_digest:
            msg = "canonical metadata digest differs between reconciled rows"
            raise _reject(msg)
        canonical_digest = digest


def validate_software_doi_resolution(resolution: dict[str, Any], original: dict[str, Any], records: dict[str, dict[str, Any]]) -> None:
    """Bind every failed command to independent passing canonical evidence."""
    if original["status"] != "failed":
        msg = "only a failed validator can carry this resolution"
        raise _reject(msg)
    failed = {index for index, execution in enumerate(original["executions"]) if execution["result"] == "failed"}
    checks = resolution["checks"]
    covered = [check["execution_index"] for check in checks]
    if not failed or len(covered) != len(set(covered)) or set(covered) != failed:
        msg = "reconcile every failed execution exactly once"
        raise _reject(msg)
    if any(execution["result"] not in {"passed", "failed"} for execution in original["executions"]):
        msg = "unexecuted commands still block readiness"
        raise _reject(msg)
    for check in checks:
        verified = records.get(check["verification_evidence_id"])
        if verified is None or verified.get("record_type") != "validation" or verified["status"] != "passed":
            msg = "verification must reference a passing predecessor validator"
            raise _reject(msg)
        source = original.get("observed_source_state")
        if not source or verified.get("observed_source_state") != source:
            msg = "verification must use the same captured source state"
            raise _reject(msg)
        inspect_manual_doi_check(original, check["execution_index"], check["original_report"])
        _reconcile_reports(original, verified, check)
