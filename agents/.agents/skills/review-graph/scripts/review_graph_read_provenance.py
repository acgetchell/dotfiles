"""Bind external instruction and own-protocol reads independently of source paths."""

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from review_graph_discovery import SourceDiscovery, bind_discovery
from review_graph_integrity import digest_bytes
from review_graph_reads import shell_words, source_read_operands


class MissingReadProvenanceError(ValueError):
    """A completed judgment omitted required instruction declarations."""


@dataclass(frozen=True)
class BoundRuntimeReads:
    """Compiler-verified external inputs, exact executions and selection dependencies."""

    inputs: tuple[tuple[str, str], ...]
    commands: tuple[str, ...]
    discoveries: tuple[SourceDiscovery, ...]


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
    from review_graph_execution import command_prefix  # noqa: PLC0415 - optional bound runner identity.
    from review_graph_session import ORIGIN_FILE, runtime_command  # noqa: PLC0415 - optional framework capture identity.

    words = shell_words(prefix)
    executable = runtime_command(Path(__file__).with_name("capture_scope.py"))
    if reference := dispatch.get("runtime_snapshot"):
        root = Path(reference["path"]).parent
        executable = command_prefix(dispatch.get("execution_context"))
        if (origin_path := root / ORIGIN_FILE).is_file() and json.loads(origin_path.read_bytes())["helper_version"] is not None:
            executable.extend(("-E", "-s"))
        executable.append(str(root / "skills/review-graph/scripts/capture_scope.py"))
    if words is None or words[: len(executable)] != executable:
        return None
    arguments = [word for word in words[len(executable) :] if not word.startswith("--output=")]
    if len(arguments) % 2 or any(arguments[index] not in {"--mode", "--repo", "--base", "--path", "--output"} for index in range(0, len(arguments), 2)):
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


def _payload_input(path: str, dispatch: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    """Bind only a regular external file containing this node's actual semantic payload."""
    if Path(path).is_relative_to(Path(dispatch["repository_root"])):
        msg = "protocol payload input must be outside the source repository"
        raise ValueError(msg)
    digest = file_identity(path)
    content = Path(path).read_bytes()
    if digest_bytes(content) != digest or json.loads(content) != payload:
        msg = "protocol payload input differs from the submitted worker payload"
        raise ValueError(msg)
    return {path: digest}


def _publication_inputs(command: str, dispatch: dict[str, Any], payload: dict[str, Any]) -> dict[str, str] | None:
    """Identify inputs to a recognized publication command, returning None for an unrelated command."""
    persistence = dispatch.get("worker_payload_persistence", {})
    publications = {shlex.join(persistence[key]) for key in ("publish_command", "command", "review_command") if key in persistence}
    if command in publications:
        return {}
    for prefix in publications:
        if not command.startswith(prefix + " < "):
            continue
        suffix = command[len(prefix) + 3 :]
        words = shell_words(suffix)
        if words is not None and len(words) == 1 and suffix == shlex.quote(words[0]):
            return _payload_input(words[0], dispatch, payload)
    return None


def _operation_inputs(command: str, dispatch: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, str], SourceDiscovery | None] | None:
    """Bind a recognized worker operation to its inputs and optional discovery query, or return None."""
    if (inputs := _publication_inputs(command, dispatch, payload)) is not None:
        inputs.update((path, file_identity(path)) for path in dispatch.get("protocol_input_paths", []))
        return inputs, None
    if (inputs := _instruction_read(command, dispatch)) is not None:
        return inputs, None
    if (output := _capture_output(command, dispatch)) is not None:
        inputs = {output: file_identity(output)}
        observation = next((item for item in dispatch.get("audit_observations", {}).values() if command == item["capture_command"]), None)
        if observation is not None:
            receipt = observation["receipt_path"]
            if not isinstance(receipt, str):
                msg = "protocol capture receipt_path must be a string"
                raise TypeError(msg)
            inputs[receipt] = file_identity(receipt)
            if json.loads(Path(receipt).read_bytes()).get("capture_digest") != inputs[output]:
                msg = "protocol capture receipt differs from its captured bytes"
                raise ValueError(msg)
        return inputs, None
    if (discovered := bind_discovery(command, dispatch)) is not None:
        query, binding = discovered
        return dict([binding]), query
    return None


def _protocol_input_bindings(dispatch: dict[str, Any]) -> dict[str, str]:
    """Check generated sidecars against the publication contract's bound canonical input."""
    paths = dispatch.get("protocol_input_paths", [])
    bindings: dict[str, str] = {path: file_identity(path) for path in paths}
    contract_path = dispatch.get("worker_payload_persistence", {}).get("input_path")
    if contract_path not in bindings:
        return bindings
    contract = json.loads(Path(contract_path).read_bytes())
    if not (reference := contract.get("compiler_preflight")):
        return bindings  # Historical contracts retain their original narrower policy.
    input_path = reference["worker_input_path"]
    if input_path not in bindings or bindings[input_path] != reference["digest"]:
        msg = "protocol input differs from its bound publication contract"
        raise ValueError(msg)
    content = Path(input_path).read_bytes()
    entry = json.loads(content)
    canonical_dispatch = entry["dispatch"]
    # The compiler separately verifies metadata transitions and reconciles
    # inherited coverage. Neither rewrites the original publication contract.
    if changed := [
        key for key, value in canonical_dispatch.items() if key not in {"external_metadata_transitions", "coverage_reuse"} and dispatch.get(key) != value
    ]:
        msg = "protocol canonical input differs from the dispatched contract: " + ", ".join(changed)
        raise ValueError(msg)
    expected = {
        **({"coverage_reuse": canonical_dispatch["coverage_reuse"]} if "coverage_reuse" in canonical_dispatch else {}),
        **{key: canonical_dispatch[key] for key in ("mode", "node_id", "owned_paths", "worker_payload_path")},
        "result_contract": entry["result_contract"],
        "schema_version": 1,
        "compiler_preflight": reference,
    }
    if contract != expected:
        msg = "protocol publication contract differs from its canonical input"
        raise ValueError(msg)
    if (execution_path := entry.get("worker_execution_path")) in bindings:
        from review_graph_views import execution_view_bytes  # noqa: PLC0415 - generated sidecar verification without initialization cycles.

        if bindings[execution_path] != digest_bytes(execution_view_bytes(entry, content)):
            msg = "protocol execution view differs from its canonical input"
            raise ValueError(msg)
    return bindings


def bind_runtime_reads(dispatch: dict[str, Any], payload: dict[str, Any]) -> BoundRuntimeReads:
    """Only dispatch-owned resources and verified capture outputs can be bound."""
    require_instruction_reads(dispatch, payload)
    root = Path(dispatch.get("repository_root", "."))
    allowed: dict[str, str] = dict(dispatch.get("runtime_input_digests", []))
    if reference := dispatch.get("runtime_snapshot"):
        from review_graph_session import verify_snapshot  # noqa: PLC0415 - optional frozen resource verification.

        manifest = verify_snapshot(reference)
        allowed[reference["path"]] = reference["digest"]
        allowed.update((str(Path(reference["path"]).parent / path), digest) for path, digest in manifest.files)
    reads: set[str] = set(payload.get("nearby_contract_owners", []))
    protocol: list[str] = []
    discoveries: list[SourceDiscovery] = []
    protocol_used = False
    for command in payload.get("commands_executed", []):
        lines = [line for line in command.split("\n") if line.strip()]
        classified, has_protocol = bool(lines), False
        for line in lines:
            if (operation := _operation_inputs(line, dispatch, payload)) is not None:
                inputs, query = operation
                allowed.update(inputs)
                reads.update(inputs)
                has_protocol = True
                protocol_used = True
                if query is not None:
                    discoveries.append(query)
            elif (operands := source_read_operands(line)) is not None:
                reads.update(operands)
            else:
                classified = False
        if classified and has_protocol:
            protocol.append(command)  # Preserve the whole original execution, including newlines.
    if protocol_used or reads.intersection(dispatch.get("protocol_input_paths", [])):
        allowed.update(_protocol_input_bindings(dispatch))
    own_payload = dispatch.get("worker_payload_path")
    if own_payload in reads:
        allowed.update(_payload_input(own_payload, dispatch, payload))
    bindings = tuple(sorted((path, allowed[path]) for path in reads if path in allowed and not Path(path).is_relative_to(root)))
    verify_runtime_inputs(bindings, str(root))
    return BoundRuntimeReads(bindings, tuple(protocol), tuple(discoveries))


def normalized_read_provenance(inputs: Any) -> dict[str, Any]:
    """Expose only compiler-bound identities, never a worker's classification."""
    if inputs is None or not (inputs.runtime_inputs or inputs.protocol_commands):
        return {}
    return {"runtime_inputs": [list(item) for item in inputs.runtime_inputs], "protocol_commands": list(inputs.protocol_commands)}
