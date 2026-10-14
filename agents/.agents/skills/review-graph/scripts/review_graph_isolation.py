"""One fresh-context boundary shared by dispatch, publication and compilation."""

import shlex
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

ISOLATION_INSTRUCTIONS = (
    "Fresh audit isolation: do not read another node's inputs, payloads, reports, or evidence, including validator/CI evidence. "
    "Keep validator evidence delegated through planned-validation IDs and requirement-bound caveats. "
    "You may read your own dispatch/schema/publication contract, raw source, supplied shared source packets, and the exact inherited "
    "coverage references explicitly dispatched to this node. Predecessor IDs do not grant access to other evidence. "
    "Record every actual read and command; an isolation failure requires a new clean worker for this node only."
)


def forbidden_artifacts(node_id: str, entries: dict[str, dict[str, Any]]) -> list[str]:
    """Bind all other node artifacts, including compact execution views."""
    forbidden: set[str] = set()
    for other_id, entry in entries.items():
        if other_id != node_id:
            # Node-addressed sidecars include sealed payloads, coverage proofs,
            # timing receipts and failed attempts created after materialization.
            forbidden.add(other_id + ".")
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
                    forbidden.update((str(Path(value)), Path(value).name))
    return sorted(forbidden)


def isolation_violations(dispatch: dict[str, Any], payload: dict[str, Any]) -> tuple[str, ...]:
    """Apply the compiler's artifact boundary to truthful command and read ledgers."""
    if dispatch.get("fresh_context") is not True or dispatch.get("mode") not in {"audit", "independent-review"}:
        return ()
    reads = [*payload.get("commands_executed", []), *payload.get("files_inspected", []), *payload.get("nearby_contract_owners", [])]
    return tuple(f"{read} -> {path}" for read in reads for path in dispatch.get("fresh_context_forbidden_artifacts", []) if _selects_artifact(read, path))


def _selects_artifact(read: str, artifact: str) -> bool:
    """Recognize literal, glob and directory selectors without executing a shell."""
    if artifact in read:
        return True
    try:
        tokens = shlex.split(read)
    except ValueError:
        tokens = read.split()
    for token in tokens:
        if any(char in token for char in "*?[") and (fnmatchcase(artifact, token) or fnmatchcase(Path(artifact).name, Path(token).name)):
            return True
        if Path(token).is_absolute() and Path(artifact).is_absolute():
            normalized = Path(token).resolve()
            if Path(artifact).resolve().is_relative_to(normalized):
                return True
    return False


class IsolationViolationError(ValueError):
    """A truthful ledger makes the fresh worker ineligible for acceptance."""


class IsolationPublicationError(ValueError):
    """A retained rejection with bounded node-local recovery instructions."""

    def __init__(self, receipt: dict[str, Any]) -> None:
        """Preserve the exact recovery receipt for CLI and library callers."""
        self.receipt = receipt
        super().__init__(receipt["message"])
