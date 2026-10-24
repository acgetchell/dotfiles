"""One evidence-bound final correction within a repair's affected verification."""

import json
from pathlib import Path
from typing import Any

from review_graph_control import read_control_file
from review_graph_integrity import digest_bytes, digest_json


def repair_origin(result: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Bind repair issuance to the run's existing external, immutable control store."""
    root = Path(result["new_plan"]["review_lifecycle"]["run_control"]["identity"]["path"]).parent
    epoch = result["repair_epoch"]
    suffix = ".verification" if epoch.get("verification_followup") else "-" + digest_json(result["new_plan"])[7:23]
    return root / f"repair-{epoch['ordinal']:03d}{suffix}.json", {
        "plan_digest": digest_json(result["new_plan"]),
        "capture_digest": digest_json(result["capture"]),
        "repair_epoch": epoch,
    }


def verify_followup_origin(document: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Bind the current plan and footprint to an immutable, ordinary repair result."""
    reference = request["previous_repair"]
    path = Path(reference["path"])
    repository = Path(document["previous_capture"]["repository_root"])
    if not path.is_absolute() or path.resolve() != path or path.is_relative_to(repository) or not path.is_file():
        msg = "verification_followup.previous_repair requires an external regular immutable repair result"
        raise ValueError(msg)
    content = path.read_bytes()
    if digest_bytes(content) != reference["digest"]:
        msg = "verification_followup.previous_repair digest differs from retained bytes"
        raise ValueError(msg)
    previous = json.loads(content)
    if not isinstance(previous, dict) or not isinstance(previous.get("repair_epoch"), dict):
        msg = "verification_followup.previous_repair must contain a complete repair result object"
        raise TypeError(msg)
    if (
        previous.get("status") != "advanced"
        or previous.get("new_plan") != document["plan"]
        or previous.get("capture") != document["previous_capture"]
        or previous.get("repair_epoch", {}).get("verification_followup")
        or previous.get("repair_epoch", {}).get("ordinal") != document["plan"]["review_lifecycle"]["repairs_completed"]
    ):
        msg = "verification_followup requires the immediately prior ordinary repair; one follow-up is permitted per batch"
        raise ValueError(msg)
    origin_path, expected = repair_origin(previous)
    if json.loads(read_control_file(origin_path)) != expected:
        msg = "verification_followup.previous_repair differs from its runtime-issued repair origin"
        raise ValueError(msg)
    if not request["reason"].strip():
        msg = "verification_followup.reason must explain the confirmed affected-verification defect"
        raise ValueError(msg)
    return previous


def verify_followup_finding(previous: dict[str, Any], request: dict[str, Any], records: list[dict[str, Any]]) -> None:
    """Require a new finding in an already repaired path; historical findings cannot reopen work."""
    record = next((item for item in records if item["evidence_id"] == request["finding_evidence_id"]), None)
    footprint = set(previous["repair_epoch"]["changed_paths"])
    state = [previous["capture"][key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")]
    if (
        record is None
        or record.get("mode") not in {"audit", "independent-review"}
        or record.get("status") != "completed"
        or record.get("observed_source_state") != state
        or not any(finding["location"].split(":", 1)[0] in footprint and not finding.get("source_findings") for finding in record.get("findings", []))
    ):
        msg = "verification_followup.finding_evidence_id must name current completed review evidence with a finding in an already repaired path"
        raise ValueError(msg)
