"""Verified full-document deltas for focused, fresh audit reconciliation."""

import difflib
from pathlib import Path
from typing import Any

from review_graph_git_objects import GitPathIdentity
from review_graph_integrity import digest_bytes
from review_graph_reuse import AuditInputIdentity, AuditReuseTransition, ReviewSourceSnapshot, regular_file_fingerprint, verify_reuse_inputs

_DIMENSIONS = ("rules", "commands", "applicability", "obligations")


def retained_input_texts(root: Path, instructions: tuple[str, ...], payload: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Retain instruction and explicitly declared recipe bytes at the original audit."""
    paths = {Path(path).relative_to(root).as_posix() for path in instructions if Path(path).is_relative_to(root)}
    paths.update(item["path"] for unit in payload.get("coverage_units", []) for item in unit.get("recipe_dependencies", []))
    result = []
    for relative in sorted(paths):
        path = root / relative
        if path.resolve() != path or not path.is_file():
            continue  # No retained regular text means no later delta reconciliation.
        try:
            result.append((relative, path.read_bytes().decode("utf-8")))
        except UnicodeError:
            continue
    return tuple(result)


def _verified_text(path: str, text: str, fingerprint: str) -> GitPathIdentity:
    identity = GitPathIdentity.parse(fingerprint)
    if (
        identity.mode not in {"100644", "100755"}
        or regular_file_fingerprint(path, text.encode(), executable=identity.mode == "100755", algorithm=identity.algorithm) != fingerprint
    ):
        msg = "instruction delta text does not match the complete captured file identity"
        raise ValueError(msg)
    return identity


def instruction_delta_candidate(  # noqa: PLR0913 - source/target proof and optional immutable replay text.
    unit: dict[str, Any],
    origin: ReviewSourceSnapshot,
    target: ReviewSourceSnapshot,
    inputs: AuditInputIdentity,
    transition: AuditReuseTransition,
    *,
    retained_after: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Prove that only declared instruction/recipe dependencies need semantic review."""
    root = Path(origin.repository_root)
    instructions = {Path(path).relative_to(root).as_posix() for path, _digest in inputs.instruction_digests if Path(path).is_relative_to(root)}
    recipes = {item["path"]: item["recipes"] for item in unit.get("recipe_dependencies", [])}
    allowed = instructions | recipes.keys()
    before, after = dict(origin.repository_path_fingerprints), dict(target.repository_path_fingerprints)
    changed = {path for path in allowed if before.get(path) != after.get(path)}
    if not changed or changed.intersection(unit["owned_paths"]):
        return []
    verify_reuse_inputs(origin, target, inputs, transition, instruction_delta_paths=frozenset(changed))
    old_texts = dict(inputs.retained_inputs)
    deltas = []
    for path in sorted(changed):
        old = old_texts[path]
        new = retained_after[path] if retained_after is not None else (root / path).read_bytes().decode("utf-8")
        old_identity, new_identity = _verified_text(path, old, before[path]), _verified_text(path, new, after[path])
        if (old_identity.mode, old_identity.algorithm) != (new_identity.mode, new_identity.algorithm):
            msg = "instruction reconciliation cannot waive file-mode or object-format changes"
            raise ValueError(msg)
        for identities, content in ((dict(inputs.instruction_digests), old), (dict(transition.instruction_digests), new)):
            if str(root / path) in identities and identities[str(root / path)] != digest_bytes(content.encode()):
                msg = "instruction text differs from the audit's full-document digest"
                raise ValueError(msg)
        deltas.append(
            {
                "path": path,
                "role": "instruction" if path in instructions else "recipe",
                "recipes": recipes.get(path, []),
                "before": old,
                "after": new,
                "before_identity": before[path],
                "after_identity": after[path],
                "diff": "".join(
                    difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile="before/" + path, tofile="after/" + path)
                ),
            }
        )
    return deltas


def effective_units(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply only compiler-bound worker decisions; pending units remain rechecks."""
    decisions = {item["unit_id"]: item for item in context.get("instruction_reconciliations", [])}
    return [
        {**unit, "disposition": "reused" if decisions.get(unit["unit_id"], {}).get("disposition") == "unchanged" else "recheck"}
        if unit["disposition"] == "instruction-review"
        else unit
        for unit in context["units"]
    ]


def _check_judgment(judgment: dict[str, Any], unit: dict[str, Any], payload: dict[str, Any]) -> None:
    assessments = judgment["assessments"]
    paths = {delta["path"] for delta in unit["input_deltas"]}
    if len(assessments) != len(paths) or {item["path"] for item in assessments} != paths or not paths <= set(payload["nearby_contract_owners"]):
        msg = "instruction reconciliation requires every changed document and truthful read attestation"
        raise ValueError(msg)
    for item in assessments:
        if any(not item[dimension]["reason"].strip() for dimension in _DIMENSIONS) or item["changed_sections_inspected"] is not True:
            msg = "instruction reconciliation needs inspected sections and reasons for all contract dimensions"
            raise ValueError(msg)
        if judgment["disposition"] == "unchanged" and any(item[dimension]["changed"] for dimension in _DIMENSIONS):
            msg = "changed contract rules, commands, applicability or obligations require source reinspection"
            raise ValueError(msg)
    if judgment["disposition"] == "uncertain" and payload["status"] != "blocked":
        msg = "uncertain instruction relevance blocks audit acceptance"
        raise ValueError(msg)
    if judgment["disposition"] == "reinspect" and not set(unit["owned_paths"]) <= set(payload["files_inspected"]):
        msg = "material instruction changes require inspection of every owned path in the affected unit"
        raise ValueError(msg)


def reconcile_instructions(context: dict[str, Any] | None, payload: dict[str, Any], *, fresh: bool) -> dict[str, Any] | None:
    """Require a fresh specialist's complete, explicit semantic delta assessment."""
    judgments = payload.get("instruction_reconciliations", [])
    if not judgments:
        if context is not None and context.get("instruction_reconciliations"):
            msg = "instruction reconciliation differs from its sealed worker payload"
            raise ValueError(msg)
        return context
    if context is None or not fresh:
        msg = "instruction reconciliation requires a fresh audit with a runtime-bound delta"
        raise ValueError(msg)
    pending = {unit["unit_id"]: unit for unit in context["units"] if unit["disposition"] == "instruction-review"}
    if len(judgments) != len(pending) or {item["unit_id"] for item in judgments} != pending.keys():
        msg = "instruction reconciliation must assess every pending unit exactly once"
        raise ValueError(msg)
    for judgment in judgments:
        _check_judgment(judgment, pending[judgment["unit_id"]], payload)
    if context.get("instruction_reconciliations", judgments) != judgments:
        msg = "instruction reconciliation differs from its sealed worker payload"
        raise ValueError(msg)
    return {**context, "instruction_reconciliations": judgments}
