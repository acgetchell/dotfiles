"""Narrow readiness reconciliation for immutable software DOI validation reports."""

import base64
import html
import json
import re
import runpy
import shlex
from datetime import date
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import Any

from review_graph_reuse import ReviewSourceSnapshot, regular_file_fingerprint, source_snapshot


class _UnusableReportError(ValueError):
    """A retained report has no usable DOI results; its bytes are still intact."""


def _reject(detail: str) -> ValueError:
    return ValueError(f"software DOI reconciliation: {detail}")


@cache
def _bibliography_parser() -> dict[str, Any]:
    """Load the citation checker's dependency-free context parser without path mutation."""
    path = Path(__file__).parents[2] / "scientific-citation-audit" / "scripts" / "bibliography_context.py"
    return runpy.run_path(str(path))


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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _UnusableReportError(f"software DOI reconciliation: cannot verify report: {exc}") from exc
    if not isinstance(rows, list) or not rows:
        msg = "report must contain DOI results"
        raise _UnusableReportError(f"software DOI reconciliation: {msg}")
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("doi"), str) or type(row.get("line")) is not int or row["line"] < 1:
            msg = "report has an invalid DOI occurrence"
            raise _UnusableReportError(f"software DOI reconciliation: {msg}")
        key = (row["doi"].casefold(), row["line"])
        if key in indexed:
            msg = "report repeats a DOI occurrence"
            raise _UnusableReportError(f"software DOI reconciliation: {msg}")
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


def _captured_cff_digest(canonical: dict[str, Any], cff: Path, capture: ReviewSourceSnapshot) -> str:
    """Prove retained CFF bytes against the captured path without reading today's file."""
    try:
        relative = cff.relative_to(capture.repository_root).as_posix()
        encoded = canonical.get("content_base64")
        if not isinstance(encoded, str):
            msg = "canonical report lacks retained CFF bytes"
            raise TypeError(msg)
        content = base64.b64decode(encoded, validate=True)
    except (TypeError, ValueError) as exc:
        raise _reject(f"cannot verify captured CFF bytes: {exc}") from exc
    captured = dict(capture.repository_path_fingerprints).get(relative)
    if captured is None:
        msg = "CITATION.cff is absent from the captured source"
        raise _reject(msg)
    if captured not in {regular_file_fingerprint(relative, content, executable=executable) for executable in (False, True)}:
        msg = "retained CFF bytes do not match the captured source"
        raise _reject(msg)
    return "sha256:" + sha256(content).hexdigest()


def _canonical_report_path(record: dict[str, Any], execution: dict[str, Any]) -> str | None:
    candidates: list[str] = [
        artifact["path"] for artifact in record["artifacts"] if artifact["kind"] == "report" and artifact["path"] in execution.get("artifact_paths", [])
    ]
    words = shlex.split(execution["command"])
    if len(words) >= 2 and words[-2] in {">", "1>"}:
        output = str((Path(execution["working_directory"]) / words[-1]).resolve())
        candidates = [path for path in candidates if path == output]
    return candidates[0] if len(candidates) == 1 else None


def _canonical_rows(record: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    rows = []
    for execution in record["executions"]:
        if execution["result"] not in {"passed", "failed"} or str(execution.get("exit_code")) not in {"0", "1"}:
            continue
        try:
            _markdown, cff = _command_inputs(execution)
        except ValueError:
            continue  # Other validators do not supply canonical software evidence.
        if cff is None:
            continue
        report_path = _canonical_report_path(record, execution)
        if report_path is None:
            continue
        try:
            report_rows = _report(record, execution, report_path)
        except _UnusableReportError:
            continue  # Preserve completed execution evidence without granting reconciliation eligibility.
        for row in report_rows.values():
            canonical = row.get("canonical_software")
            if row.get("status") == "OK" and isinstance(canonical, dict):
                rows.append((cff, canonical))
    return rows


def captured_software_inputs(record: dict[str, Any], capture: dict[str, Any]) -> dict[str, str]:
    """Derive compact CFF bindings without discarding completed validation results."""
    rows = _canonical_rows(record)
    if not rows:
        return {}
    snapshot = source_snapshot(capture)
    snapshot.verify()
    if list(snapshot.source_state) != record["observed_source_state"]:
        msg = "CFF capture differs from the validator's observed source state"
        raise _reject(msg)
    bindings: dict[str, str] = {}
    unproven: set[str] = set()
    for cff, canonical in rows:
        try:
            bindings[str(cff)] = _captured_cff_digest(canonical, cff, snapshot)
        except ValueError:
            unproven.add(str(cff))
    return {path: digest for path, digest in bindings.items() if path not in unproven}


def captured_doi_inputs(record: dict[str, Any], capture: dict[str, Any]) -> dict[str, str]:
    """Bind retained bibliography bytes to the validator's immutable source capture."""
    if not any("validate_reference_dois.py" in execution.get("command", "") for execution in record["executions"]):
        return {}
    try:
        snapshot = source_snapshot(capture)
        snapshot.verify()
    except TypeError, ValueError:
        return {}  # A legacy capture cannot grant bibliography reconciliation eligibility.
    if list(snapshot.source_state) != record["observed_source_state"]:
        msg = "bibliography capture differs from observed source state"
        raise _reject(msg)
    bindings: dict[str, str] = {}
    for execution in record["executions"]:
        try:
            markdown, _cff = _command_inputs(execution)
            report_path = _canonical_report_path(record, execution)
            if report_path is None:
                continue
            rows = _report(record, execution, report_path)
            digest = _bibliography_digest(rows, markdown, snapshot)
            if digest is not None:
                bindings[str(markdown)] = digest
        except KeyError, TypeError, ValueError:
            continue  # Older and unrelated reports remain valid evidence, without reconciliation eligibility.
    return bindings


def _bibliography_digest(rows: dict[tuple[str, int], dict[str, Any]], markdown: Path, snapshot: ReviewSourceSnapshot) -> str | None:
    """Require every reported occurrence to carry the same captured Markdown bytes."""
    digest = None
    for row in rows.values():
        source = row.get("source", {})
        if not isinstance(source, dict) or source.get("path") != str(markdown):
            msg = "report source differs from executed Markdown input"
            raise _reject(msg)
        digest = _captured_cff_digest(source, markdown, snapshot)
        if source.get("digest") != digest:
            msg = "bibliography digest differs from retained bytes"
            raise _reject(msg)
    return digest


def _canonical_match(row: dict[str, Any], cff: Path, captured_inputs: dict[str, str]) -> None:
    canonical = row.get("canonical_software")
    if not isinstance(canonical, dict) or canonical.get("path") != str(cff):
        msg = "canonical identity does not name the executed CITATION.cff"
        raise _reject(msg)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(canonical.get("digest", ""))):
        msg = "canonical metadata has no content digest"
        raise _reject(msg)
    if canonical["digest"] != captured_inputs.get(str(cff)):
        msg = "canonical metadata digest does not match captured CFF bytes"
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
        if "source" in old and any(old["source"].get(field) != source.get(field) for field in ("path", "digest")):
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
        _canonical_match(new, cff, verified.get("captured_software_inputs", {}))
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


def _primary_year(row: dict[str, Any], occurrence: dict[str, Any]) -> None:
    """Verify the retained primary record supports the same identity and local year."""
    if row.get("mismatched_fields") != ["year"] or (row.get("title_score") or 0) < 0.8 or row.get("author_score") != 1.0:
        msg = "scholarly resolution requires a year-only disagreement with matching title and authors"
        raise _reject(msg)
    primary = occurrence["primary_record"]
    path = Path(primary["path"])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        msg = "primary evidence must be an absolute regular file"
        raise _reject(msg)
    content = path.read_bytes()
    if "sha256:" + sha256(content).hexdigest() != primary["digest"]:
        msg = "primary evidence bytes changed"
        raise _reject(msg)
    if not primary["url"].startswith("https://") or primary["authority"] not in {"publisher", "journal-archive"}:
        msg = "primary evidence requires a publisher or journal archive URL"
        raise _reject(msg)
    date.fromisoformat(primary["retrieved_on"])
    if primary["doi"].casefold() != row["doi"].casefold() or _identity(primary["title"]) != _identity(row["resolved_title"]):
        msg = "primary evidence identifies a different DOI or title"
        raise _reject(msg)
    if {_identity(name) for name in primary["authors"]} != {_identity(name) for name in row["resolved_authors"]}:
        msg = "primary evidence identifies different authors"
        raise _reject(msg)
    year = primary["publication_year"]
    _publication_disagreement(row, occurrence, year)
    _primary_excerpt(primary, content)
    if occurrence["disposition"] != "retain-local-publication-year" or not occurrence["reviewer"].strip() or not occurrence["reason"].strip():
        msg = "scholarly disagreement requires an explicit reviewer disposition"
        raise _reject(msg)


def _publication_disagreement(row: dict[str, Any], occurrence: dict[str, Any], year: str) -> None:
    """Identify the particular resolver date when publication date fields conflict."""
    field = occurrence.get("resolver_field", "resolved_year")
    provenance = row.get("date_provenance", {})
    resolver = row.get("resolved_year") if field == "resolved_year" else provenance.get(field) if isinstance(provenance, dict) else None
    if row.get("local_years") != [year] or occurrence["field"] != "year" or occurrence["resolver_value"] != resolver or resolver == year:
        msg = "publication-year disposition differs from the exact local/resolver disagreement"
        raise _reject(msg)


def _primary_excerpt(primary: dict[str, Any], content: bytes) -> None:
    """Check the reviewer's extracted facts against retained primary evidence."""
    year = primary["publication_year"]
    text = html.unescape(re.sub(r"<[^>]+>", " ", content.decode("utf-8")))
    excerpt = primary["excerpt"]
    normalized = f" {_identity(excerpt)} "
    if normalized not in f" {_identity(text)} ":
        msg = "primary excerpt is absent from retained evidence"
        raise _reject(msg)
    facts = (primary["doi"], primary["title"], *primary["authors"])
    without_doi = re.sub(re.escape(primary["doi"]), " ", excerpt, flags=re.IGNORECASE)
    if not all(f" {_identity(value)} " in normalized for value in facts) or f" {year} " not in f" {_identity(without_doi)} ":
        msg = "primary excerpt does not support DOI, title, authors, and publication year"
        raise _reject(msg)


def _source_row(row: dict[str, Any], markdown: Path, original: dict[str, Any], retained: bytes | None = None) -> dict[str, Any]:
    source = row.get("source", {})
    if not isinstance(source, dict):
        msg = "scholarly report has an invalid bibliography source"
        raise _reject(msg)
    if retained is None and (source.get("path") != str(markdown) or source.get("digest") != original.get("captured_doi_inputs", {}).get(str(markdown))):
        msg = "scholarly report is not bound to captured bibliography bytes"
        raise _reject(msg)
    content = retained if retained is not None else base64.b64decode(source["content_base64"], validate=True)
    if source and (source.get("path") != str(markdown) or "sha256:" + sha256(content).hexdigest() != source.get("digest")):
        msg = "retained bibliography bytes changed"
        raise _reject(msg)
    lines = content.decode("utf-8").splitlines()
    index = row["line"] - 1
    if index >= len(lines) or row["doi"].casefold() not in lines[index].casefold():
        msg = "DOI occurrence is absent from captured bibliography line"
        raise _reject(msg)
    parser = _bibliography_parser()
    entry = parser["collect_entry"](lines, index)
    years = list(parser["publication_years"](entry, row["doi"]))
    if "local_years" in row and row["local_years"] != years:
        msg = "local publication year differs from captured bibliography context"
        raise _reject(msg)
    return {**row, "local_years": years, "mismatched_fields": ["year"]}


def _year_only(row: dict[str, Any]) -> bool:
    """Recognize new typed disagreements and the old checker's exact year-only result."""
    return bool(
        row.get("status") == "MISMATCH"
        and (
            row.get("mismatched_fields") == ["year"]
            or ("mismatched_fields" not in row and row.get("message") == "resolved year does not appear in local entry")
        )
    )


def _retained_bibliography(binding: dict[str, Any], markdown: Path, original: dict[str, Any]) -> bytes:
    """Reconcile historical reports using already retained, source-bound evidence."""
    contents = []
    for prefix in ("capture", "bibliography"):
        path = Path(binding[f"{prefix}_path"])
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            msg = "historical source evidence requires absolute regular files"
            raise _reject(msg)
        content = path.read_bytes()
        if "sha256:" + sha256(content).hexdigest() != binding[f"{prefix}_digest"]:
            msg = "historical source evidence bytes changed"
            raise _reject(msg)
        contents.append(content)
    snapshot = source_snapshot(json.loads(contents[0]))
    snapshot.verify()
    relative = markdown.relative_to(snapshot.repository_root).as_posix()
    fingerprints = dict(snapshot.repository_path_fingerprints)
    if list(snapshot.source_state) != original["observed_source_state"] or relative in snapshot.repository_symlink_paths:
        msg = "historical source evidence differs from validator source state"
        raise _reject(msg)
    if fingerprints.get(relative) not in {regular_file_fingerprint(relative, contents[1], executable=mode) for mode in (False, True)}:
        msg = "historical bibliography bytes do not match captured source"
        raise _reject(msg)
    return contents[1]


def validate_scholarly_doi_resolution(resolution: dict[str, Any], original: dict[str, Any], records: dict[str, dict[str, Any]]) -> None:
    """Resolve only primary-supported dates, optionally alongside canonical software rows."""
    failed = {index for index, execution in enumerate(original["executions"]) if execution["result"] == "failed"}
    covered = [check["execution_index"] for check in resolution["checks"]]
    if original["status"] != "failed" or not failed or len(covered) != len(set(covered)) or set(covered) != failed:
        msg = "scholarly resolution must cover every failed execution exactly once"
        raise _reject(msg)
    if any(execution["result"] not in {"passed", "failed"} for execution in original["executions"]):
        msg = "unexecuted commands still block scholarly readiness"
        raise _reject(msg)
    for check in resolution["checks"]:
        inspect_manual_doi_check(original, check["execution_index"], check["original_report"])
        execution = _execution(original, check["execution_index"], "failed")
        markdown, _cff = _command_inputs(execution)
        rows = _report(original, execution, check["original_report"])
        occurrences = {(item["doi"].casefold(), item["line"]): item for item in check["occurrences"]}
        if len(occurrences) != len(check["occurrences"]):
            msg = "scholarly resolution repeats an occurrence"
            raise _reject(msg)
        scholarly = {key for key, row in rows.items() if _year_only(row)}
        if not scholarly or set(occurrences) != scholarly:
            msg = "reconcile exactly the year-only scholarly occurrences"
            raise _reject(msg)
        retained = _retained_bibliography(check["source_evidence"], markdown, original) if "source_evidence" in check else None
        for key in scholarly:
            checked = _source_row(rows[key], markdown, original, retained)
            _primary_year(checked, occurrences[key])
        software = {key for key, row in rows.items() if row.get("status") != "OK"} - scholarly
        verification = check.get("software_verification")
        if not software and verification is None:
            continue
        if verification is None:
            msg = "unresolved non-scholarly DOI occurrences still block readiness"
            raise _reject(msg)
        _scholarly_software_followup(verification, original, records, markdown, rows)


def _scholarly_software_followup(
    verification: dict[str, Any], original: dict[str, Any], records: dict[str, dict[str, Any]], markdown: Path, rows: dict[tuple[str, int], dict[str, Any]]
) -> None:
    """Prove only canonical software rows changed in an accepted mixed report."""
    software = {key for key, row in rows.items() if row.get("status") != "OK" and not _year_only(row)}
    verified = records.get(verification["evidence_id"])
    if verified is None or verified.get("record_type") != "validation" or verified.get("observed_source_state") != original["observed_source_state"]:
        msg = "software follow-up requires accepted evidence from the same captured source"
        raise _reject(msg)
    index = verification["execution_index"]
    if type(index) is not int or not 0 <= index < len(verified["executions"]):
        msg = "software follow-up execution index is outside accepted evidence"
        raise _reject(msg)
    new_execution = _execution(verified, index, "passed" if verified["executions"][index]["result"] == "passed" else "failed")
    new_markdown, cff = _command_inputs(new_execution)
    new_rows = _report(verified, new_execution, verification["report"])
    if markdown != new_markdown or cff is None or rows.keys() != new_rows.keys():
        msg = "software follow-up must cover the original input and every occurrence"
        raise _reject(msg)
    for key, old in rows.items():
        new = new_rows[key]
        if any(old.get(field) != new.get(field) for field in ("resolved_title", "resolved_year", "resolved_authors", "resolved_container")):
            msg = "source or resolved identity changed during software follow-up"
            raise _reject(msg)
        if "source" in old and any(old["source"].get(field) != new.get("source", {}).get(field) for field in ("path", "digest")):
            msg = "Markdown source changed during software follow-up"
            raise _reject(msg)
        if key in software:
            if new.get("status") != "OK" or new.get("local_status") != "INSUFFICIENT_CONTEXT" or old.get("status") not in {"INSUFFICIENT_CONTEXT", "MISMATCH"}:
                msg = "non-scholarly failure is not a canonical software pointer"
                raise _reject(msg)
            _canonical_match(new, cff, verified.get("captured_software_inputs", {}))
        elif new.get("status") != old.get("status") or (_year_only(old) and not _year_only(new)):
            msg = "software follow-up changed scholarly validation history"
            raise _reject(msg)
