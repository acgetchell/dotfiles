"""Bind external instruction and own-protocol reads independently of source paths."""

import json
import shlex
from pathlib import Path
from typing import Any

from review_graph_integrity import digest_bytes
from review_graph_reads import shell_words, source_read_operands


class MissingReadProvenanceError(ValueError):
    """A completed judgment omitted required instruction declarations."""


def file_identity(path: str) -> str:
    """Read one concrete regular file without symlink traversal."""
    target = Path(path)
    if not target.is_absolute() or target.resolve() != target or not target.is_file():
        msg = f"runtime read requires an existing absolute regular file without symlinks: {path}"
        raise ValueError(msg)
    return digest_bytes(target.read_bytes())


def verify_runtime_inputs(inputs: tuple[tuple[str, str], ...], repository: str) -> None:
    """Reject changed, missing, or repository files relabelled as external reads."""
    root = Path(repository)
    for path, digest in inputs:
        if Path(path).is_relative_to(root) or file_identity(path) != digest:
            msg = f"runtime read identity changed or is not external: {path}"
            raise ValueError(msg)


def require_instruction_reads(dispatch: dict[str, Any], payload: dict[str, Any]) -> None:
    """Check declarations, not comprehension or whether a command actually ran."""
    if payload.get("status") not in {"completed", "no-findings"}:
        return
    root = Path(dispatch.get("repository_root", "."))
    declared = {str(root / path) for path in payload.get("nearby_contract_owners", [])}
    # An instruction under owned scope is correctly recorded in files_inspected.
    declared.update(str(root / path) for path in payload.get("files_inspected", []))
    missing = set(dispatch.get("required_read_paths", [])) - declared
    if missing:
        msg = "required instruction-read provenance missing from nearby_contract_owners (or owned files_inspected): " + ", ".join(sorted(missing))
        raise MissingReadProvenanceError(msg)


def _capture_output(command: str, dispatch: dict[str, Any]) -> str | None:  # noqa: PLR0911 - reject every unbound protocol boundary.
    """Bind the framework's exact capture operation and its observed JSON output."""
    prefix = dispatch.get("state_verification_command", "")
    observation = next((item for item in dispatch.get("audit_observations", {}).values() if command == item["capture_command"]), None)
    if not prefix or (observation is None and not command.startswith(prefix + " > ")):
        return None
    from review_graph_session import runtime_command  # noqa: PLC0415 - optional framework capture identity.

    words = shell_words(prefix)
    executable = runtime_command(Path(__file__).with_name("capture_scope.py"))
    if words is None or words[: len(executable)] != executable:
        return None
    arguments = words[len(executable) :]
    if len(arguments) % 2 or any(arguments[index] not in {"--mode", "--repo", "--base", "--path"} for index in range(0, len(arguments), 2)):
        return None
    suffix = shlex.quote(observation["capture_path"]) if observation is not None else command[len(prefix) + 3 :]
    try:
        outputs = shlex.split(suffix)
    except ValueError:
        return None
    if len(outputs) != 1 or suffix != shlex.quote(outputs[0]):
        return None
    path = outputs[0]
    if Path(path).is_relative_to(Path(dispatch["repository_root"])):
        return None
    from review_graph_reuse import source_snapshot  # noqa: PLC0415 - identity module cycle, parsed only for protocol captures.

    try:
        file_identity(path)
        snapshot = source_snapshot(json.loads(Path(path).read_bytes()))
        snapshot.verify()
    except OSError, ValueError, TypeError:
        # A failed capture stays in the ledger as an unclassified command. It
        # cannot certify protocol provenance or prevent a blocked submission.
        return None
    states = [tuple(dispatch["source_state"])]
    states.extend(
        tuple(item["after"][key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint"))
        for item in dispatch.get("external_metadata_transitions", [])
    )
    return path if snapshot.repository_root == dispatch["repository_root"] and snapshot.source_state in states else None


def _instruction_read(command: str, dispatch: dict[str, Any]) -> dict[str, str] | None:
    """Recognize only this dispatch's verified, bounded full-text reader."""
    context = dispatch.get("instruction_context")
    words = shell_words(command)
    if context is None or words is None:
        return None
    prefix = context["read_command"]
    suffix = words[len(prefix) :]
    if words[: len(prefix)] != prefix or len(suffix) != 4 or suffix[0] != "--path" or suffix[2] != "--chunk":
        return None
    if suffix[1] not in dispatch["instruction_paths"]:
        return None
    try:
        chunk = int(suffix[3])
    except ValueError:
        return None
    from review_graph_instructions import InstructionChunkOutOfRangeError, load_manifest, read_manifest_chunk  # noqa: PLC0415 - bounded reader uses this module's file identity helper.

    reference = context["manifest"]
    manifest_path = Path(reference["path"])
    manifest = load_manifest(manifest_path, reference["digest"])
    try:
        read_manifest_chunk(manifest, suffix[1], chunk)
    except InstructionChunkOutOfRangeError:
        # A failed read remains an unclassified command in blocked evidence.
        return None
    record = next((item for item in manifest["files"] if item["path"] == suffix[1]), None)
    if record is None:
        msg = "instruction file is not in the bound manifest"
        raise ValueError(msg)
    return {reference["path"]: reference["digest"], record["snapshot_path"]: record["digest"], record["path"]: record["digest"]}


def bind_runtime_reads(dispatch: dict[str, Any], payload: dict[str, Any]) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """Only dispatch-owned resources and verified capture outputs can be bound."""
    require_instruction_reads(dispatch, payload)
    root = Path(dispatch.get("repository_root", "."))
    allowed: dict[str, str] = dict(dispatch.get("runtime_input_digests", []))
    if reference := dispatch.get("runtime_snapshot"):
        from review_graph_session import verify_snapshot  # noqa: PLC0415 - optional frozen resource verification.

        manifest = verify_snapshot(reference)
        allowed[reference["path"]] = reference["digest"]
        allowed.update((str(Path(reference["path"]).parent / path), digest) for path, digest in manifest.files)
    allowed.update((path, file_identity(path)) for path in dispatch.get("protocol_input_paths", []))
    reads: set[str] = set(payload.get("nearby_contract_owners", []))
    protocol: list[str] = []
    persistence = dispatch.get("worker_payload_persistence", {})
    publications = {shlex.join(persistence[key]) for key in ("publish_command", "command", "review_command") if key in persistence}
    for command in payload.get("commands_executed", []):
        if command in publications:
            protocol.append(command)
            reads.update(dispatch.get("protocol_input_paths", []))
        elif (instruction_inputs := _instruction_read(command, dispatch)) is not None:
            allowed.update(instruction_inputs)
            reads.update(instruction_inputs)
            protocol.append(command)
        elif (output := _capture_output(command, dispatch)) is not None:
            allowed[output] = file_identity(output)
            reads.add(output)
            observation = next((item for item in dispatch.get("audit_observations", {}).values() if command == item["capture_command"]), None)
            if observation is not None:
                receipt = observation["receipt_path"]
                allowed[receipt] = file_identity(receipt)
                reads.add(receipt)
            protocol.append(command)
        elif (operands := source_read_operands(command)) is not None:
            reads.update(operands)
    bindings = tuple(sorted((path, allowed[path]) for path in reads if path in allowed and not Path(path).is_relative_to(root)))
    verify_runtime_inputs(bindings, str(root))
    return bindings, tuple(protocol)


def normalized_read_provenance(inputs: Any) -> dict[str, Any]:
    """Expose only compiler-bound identities, never a worker's classification."""
    if inputs is None or not (inputs.runtime_inputs or inputs.protocol_commands):
        return {}
    return {"runtime_inputs": [list(item) for item in inputs.runtime_inputs], "protocol_commands": list(inputs.protocol_commands)}
