"""Parse the standard compiled validation record before handoff or reuse."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from review_graph_integrity import digest_bytes
from review_graph_plan import (
    VALIDATION_ARTIFACT_DIGEST_MODES,
    ValidationEvidence,
    ValidationEvidenceExpectation,
    ValidationUnit,
    _validation_native_result_blockers,
    assess_validation_evidence,
    validation_command_identity_digest,
    validation_environment_digest,
    validation_execution_result_blockers,
)
from review_graph_reuse import WORKTREE_SELECTION_ALGORITHM, ReviewSourceSnapshot, source_snapshot
from review_graph_validation_contracts import CONTRACT_PATH, ContractBinding, ContractGitInput, object_fields

if TYPE_CHECKING:
    from collections.abc import Callable


class ValidationStatus(StrEnum):
    """Finite dispositions of a standard validation result."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ExecutionResult(StrEnum):
    """Finite outcomes of an individual command."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not-run"


class FailureKind(StrEnum):
    """A valid failed check may describe a source or an execution failure."""

    SOURCE = "source"
    INFRASTRUCTURE = "infrastructure"
    TIMEOUT = "timeout"
    INCONCLUSIVE = "inconclusive"


class GitDependencyKind(StrEnum):
    """The existing standard semantic Git dependency categories."""

    SOURCE_DISCOVERY = "source-discovery"
    INPUT_SELECTION = "input-selection"
    INDEX = "index"
    HEAD = "head"
    HISTORY = "history"


def _object(raw: object, label: str) -> dict[str, object]:
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        msg = f"{label} must be an object with string keys"
        raise TypeError(msg)
    return {key: value for key, value in raw.items() if isinstance(key, str)}


def _text(raw: object, label: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        msg = f"{label} must be a nonempty string"
        raise ValueError(msg)
    return raw


def _digest(raw: object, label: str) -> str:
    value = _text(raw, label)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        msg = f"{label} must be a SHA-256 digest"
        raise ValueError(msg)
    return value


def _array(raw: object, label: str) -> tuple[object, ...]:
    if not isinstance(raw, (list, tuple)):
        msg = f"{label} must be an array"
        raise TypeError(msg)
    return tuple(raw)


def _texts(raw: object, label: str) -> tuple[str, ...]:
    return tuple(_text(value, label) for value in _array(raw, label))


def _require_tuple(raw: object, element_type: type, label: str) -> None:
    if not isinstance(raw, tuple) or any(not isinstance(item, element_type) for item in raw):
        msg = f"{label} must be an immutable tuple of {element_type.__name__}"
        raise TypeError(msg)


@dataclass(frozen=True, slots=True)
class ValidationExecution:
    """A command outcome with result-dependent exit and timing invariants."""

    command: str
    working_directory: str
    executor: str
    evidence: str
    result: ExecutionResult
    exit_code: int | str | None
    elapsed: int | float | str | None
    artifact_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject invalid construction as well as invalid JSON."""
        _text(self.command, "execution command")
        _text(self.working_directory, "execution working_directory")
        _text(self.executor, "execution executor")
        _text(self.evidence, "execution evidence")
        if not isinstance(self.result, ExecutionResult) or isinstance(self.exit_code, bool) or isinstance(self.elapsed, bool):
            msg = "execution requires a typed result and non-boolean exit/timing values"
            raise TypeError(msg)
        blockers = validation_execution_result_blockers(result=self.result, exit_code=self.exit_code, elapsed=self.elapsed, label="execution")
        if blockers:
            raise ValueError("; ".join(blockers))
        _require_tuple(self.artifact_paths, str, "execution artifact_paths")
        if len(set(self.artifact_paths)) != len(self.artifact_paths) or any(not path.strip() for path in self.artifact_paths):
            msg = "execution artifact paths must be unique and nonempty"
            raise TypeError(msg)

    @classmethod
    def from_raw(cls, raw: object) -> ValidationExecution:
        """Parse one already schema-bound execution into immutable data."""
        data = _object(raw, "execution")
        exit_code, elapsed = data.get("exit_code"), data.get("elapsed")
        if not isinstance(exit_code, (int, str, type(None))) or not isinstance(elapsed, (int, float, str, type(None))):
            msg = "execution exit_code and elapsed have invalid types"
            raise TypeError(msg)
        return cls(
            _text(data.get("command"), "execution command"),
            _text(data.get("working_directory"), "execution working_directory"),
            _text(data.get("executor"), "execution executor"),
            _text(data.get("evidence"), "execution evidence"),
            ExecutionResult(_text(data.get("result"), "execution result")),
            exit_code,
            elapsed,
            _texts(data.get("artifact_paths"), "execution artifact_paths"),
        )


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """One runtime-observed validation artifact identity."""

    path: str
    digest: str
    digest_mode: str
    kind: str
    repository_status: str

    def __post_init__(self) -> None:
        """Retain the same identity categories as the standard payload."""
        _text(self.path, "artifact path")
        _digest(self.digest, "artifact digest")
        if (
            self.digest_mode not in VALIDATION_ARTIFACT_DIGEST_MODES | {"absent-v1"}
            or self.kind not in {"build", "cache", "coverage", "log", "report", "test-result", "other"}
            or self.repository_status not in {"ignored", "outside-repository"}
        ):
            msg = "artifact identity has an unsupported mode, kind, or repository status"
            raise ValueError(msg)
        if not self.exists and self.digest != digest_bytes(b"absent"):
            msg = "absent artifact requires the canonical absence identity"
            raise ValueError(msg)

    @property
    def exists(self) -> bool:
        """Distinguish permitted absent outputs from observed artifact contents."""
        return self.digest_mode != "absent-v1"

    @classmethod
    def from_raw(cls, raw: object) -> ArtifactIdentity:
        """Parse a compiler-observed artifact, never a worker-invented hash."""
        data = _object(raw, "artifact")
        return cls(
            _text(data.get("path"), "artifact path"),
            _digest(data.get("artifact_digest"), "artifact digest"),
            _text(data.get("artifact_digest_mode"), "artifact digest_mode"),
            _text(data.get("kind"), "artifact kind"),
            _text(data.get("repository_status"), "artifact repository_status"),
        )


@dataclass(frozen=True, slots=True)
class GitDependency:
    """Immutable semantic dependency from the standard command ledger."""

    kind: GitDependencyKind
    reason: str
    command: str | None
    selection_algorithm: str | None = None

    def __post_init__(self) -> None:
        """Reject unsupported categories and empty reasons at construction."""
        if not isinstance(self.kind, GitDependencyKind):
            msg = "Git dependency requires a typed kind"
            raise TypeError(msg)
        _text(self.reason, "Git dependency reason")
        if self.command is not None:
            _text(self.command, "Git dependency command")
        if self.kind == GitDependencyKind.INPUT_SELECTION:
            if self.command is None or self.selection_algorithm != WORKTREE_SELECTION_ALGORITHM:
                msg = f"input-selection requires an exact executed command and selection_algorithm={WORKTREE_SELECTION_ALGORITHM!r}"
                raise ValueError(msg)
        elif self.selection_algorithm is not None:
            msg = "selection_algorithm applies only to input-selection dependencies"
            raise ValueError(msg)

    @classmethod
    def from_raw(cls, raw: object) -> GitDependency:
        """Parse the standard dependency declaration."""
        data = _object(raw, "Git dependency")
        command = data.get("command")
        return cls(
            GitDependencyKind(_text(data.get("kind"), "Git dependency kind")),
            _text(data.get("reason"), "Git dependency reason"),
            _text(command, "Git dependency command") if command is not None else None,
            _text(data["selection_algorithm"], "selection algorithm") if "selection_algorithm" in data else None,
        )


@dataclass(frozen=True, slots=True)
class ValidationPayload:
    """Parsed semantic output in the existing standard worker format."""

    status: ValidationStatus
    executions: tuple[ValidationExecution, ...]
    limitations: tuple[str, ...]
    git_dependencies: tuple[GitDependency, ...] | None
    failure_kind: FailureKind | None = None
    artifacts: tuple[ArtifactIdentity, ...] = ()

    def __post_init__(self) -> None:
        """Preserve format and semantic invariants before any publication."""
        if not isinstance(self.status, ValidationStatus):
            msg = "validation payload requires a typed status"
            raise TypeError(msg)
        _require_tuple(self.executions, ValidationExecution, "validation executions")
        _require_tuple(self.limitations, str, "validation limitations")
        _require_tuple(self.artifacts, ArtifactIdentity, "validation artifacts")
        if len({artifact.path for artifact in self.artifacts}) != len(self.artifacts):
            msg = "validation artifact roots must be unique"
            raise ValueError(msg)
        if self.git_dependencies is not None:
            _require_tuple(self.git_dependencies, GitDependency, "validation git_dependencies")
        if any(not item.strip() for item in self.limitations):
            msg = "validation limitations must be nonempty"
            raise ValueError(msg)
        _require_disposition(self.status, self.executions, self.limitations)
        if self.failure_kind is not None and (not isinstance(self.failure_kind, FailureKind) or self.status != ValidationStatus.FAILED):
            msg_0 = "failure_kind requires a typed category and failed validation"
            raise ValueError(msg_0)
        _require_git_dependencies(self.executions, self.git_dependencies)

    @classmethod
    def from_raw(cls, raw: object) -> ValidationPayload:
        """Parse untrusted transport once into finite, immutable fields."""
        data = object_fields(
            raw,
            "validation payload",
            required={"schema_version", "status", "executions", "limitations"},
            optional={"git_dependencies", "failure_kind", "artifacts", "native_ci"},
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != 3:
            msg = "unsupported validation format; only version 3 is accepted"
            raise ValueError(msg)
        dependencies = data.get("git_dependencies")
        return cls(
            ValidationStatus(_text(data.get("status"), "validation status")),
            tuple(ValidationExecution.from_raw(item) for item in _array(data.get("executions"), "validation executions")),
            _texts(data.get("limitations"), "validation limitations"),
            tuple(GitDependency.from_raw(item) for item in _array(dependencies, "validation git_dependencies")) if "git_dependencies" in data else None,
            FailureKind(_text(data["failure_kind"], "failure_kind")) if "failure_kind" in data else None,
            tuple(ArtifactIdentity.from_raw(item) for item in _array(data.get("artifacts", []), "validation artifacts")),
        )


@dataclass(frozen=True, slots=True)
class ValidationRecord:
    """Trusted format of a compiler-bound validation handoff, independent of reuse."""

    node_id: str
    evidence_id: str
    status: ValidationStatus
    source_state: tuple[str, str, str]
    command_digest: str
    environment_digest: str
    artifact_digest: str
    executions: tuple[ValidationExecution, ...]
    artifacts: tuple[ArtifactIdentity, ...]
    limitations: tuple[str, ...]
    git_dependencies: tuple[GitDependency, ...] | None
    source_inputs: ReviewSourceSnapshot | None = None
    contract_binding: ContractBinding | None = None
    failure_kind: FailureKind | None = None
    native_ci_heads: tuple[str, ...] = ()

    def __post_init__(self) -> None:  # noqa: C901 - validate independent compound record invariants at construction.
        """Make invalid construction fail before the record can be consumed."""
        _text(self.node_id, "validation node_id")
        _text(self.evidence_id, "validation evidence_id")
        for value in (self.command_digest, self.environment_digest, self.artifact_digest):
            _digest(value, "validation identity")
        _require_tuple(self.source_state, str, "validation source_state")
        if not isinstance(self.status, ValidationStatus) or len(self.source_state) != 3 or any(not value for value in self.source_state):
            msg = "validation requires a typed status and three source fingerprints"
            raise ValueError(msg)
        _require_tuple(self.executions, ValidationExecution, "validation executions")
        _require_tuple(self.artifacts, ArtifactIdentity, "validation artifacts")
        _require_tuple(self.limitations, str, "validation limitations")
        if self.git_dependencies is not None:
            _require_tuple(self.git_dependencies, GitDependency, "validation git_dependencies")
        if any(not item.strip() for item in self.limitations):
            msg = "validation limitations must be nonempty"
            raise ValueError(msg)
        _require_disposition(self.status, self.executions, self.limitations)
        _require_git_dependencies(self.executions, self.git_dependencies)
        if self.contract_binding is not None and (not isinstance(self.contract_binding, ContractBinding) or self.source_inputs is None):
            msg_0 = "validation contract requires typed binding and captured source inputs"
            raise TypeError(msg_0)
        if self.failure_kind is not None and (not isinstance(self.failure_kind, FailureKind) or self.status != ValidationStatus.FAILED):
            msg_0 = "failure_kind requires a typed category and failed validation"
            raise ValueError(msg_0)
        _require_tuple(self.native_ci_heads, str, "native CI heads")
        if any(not head.strip() for head in self.native_ci_heads):
            msg = "native CI requires a concrete exact commit identity"
            raise ValueError(msg)
        paths = {artifact.path for artifact in self.artifacts}
        present_paths = {artifact.path for artifact in self.artifacts if artifact.exists}
        if len(paths) != len(self.artifacts) or any(set(execution.artifact_paths) - present_paths for execution in self.executions):
            msg = "validation artifact references require unique observed artifact roots"
            raise ValueError(msg)
        if self.source_inputs is not None:
            self.source_inputs.verify()
            if self.contract_binding is not None:
                self.contract_binding.verify_inputs(self.source_inputs)
            if self.source_inputs.source_state != self.source_state:
                msg = "validation source inputs differ from its observed source state"
                raise ValueError(msg)
        if any(dependency.kind == GitDependencyKind.INPUT_SELECTION for dependency in self.git_dependencies or ()) and (
            self.source_inputs is None or self.source_inputs.repository_selection_paths is None
        ):
            msg = "input-selection validation requires runtime-captured selection membership; recapture before execution"
            raise ValueError(msg)

    @classmethod
    def from_raw(cls, raw: object) -> ValidationRecord:
        """Parse the existing normalized record after artifact/native verification."""
        data = _object(raw, "validation record")
        if data.get("record_type") != "validation" or data.get("mode") != "validation":
            msg = "validation record requires the standard validation type and mode"
            raise ValueError(msg)
        state = _texts(data.get("observed_source_state"), "validation source_state")
        if len(state) != 3:
            msg = "validation source_state requires three fingerprints"
            raise ValueError(msg)
        payload = ValidationPayload.from_raw(
            {key: value for key, value in data.items() if key in {"schema_version", "status", "executions", "limitations", "git_dependencies", "failure_kind"}}
        )
        inputs = data.get("source_inputs")
        return cls(
            _text(data.get("node_id"), "validation node_id"),
            _text(data.get("evidence_id"), "validation evidence_id"),
            payload.status,
            (state[0], state[1], state[2]),
            _digest(data.get("command_identity_digest"), "validation command_digest"),
            _digest(data.get("environment_digest"), "validation environment_digest"),
            _digest(data.get("artifact_digest"), "validation artifact_digest"),
            payload.executions,
            tuple(ArtifactIdentity.from_raw(item) for item in _array(data.get("artifacts"), "validation artifacts")),
            payload.limitations,
            payload.git_dependencies,
            source_snapshot(_object(inputs, "validation source_inputs")) if inputs is not None else None,
            ContractBinding.from_raw(data["contract_binding"]) if "contract_binding" in data else None,
            payload.failure_kind,
            tuple(
                _text(_object(item, "native CI result").get("head_sha"), "native CI head") for item in _array(data.get("native_ci", []), "native CI results")
            ),
        )


@dataclass(frozen=True, slots=True)
class VerifiedValidationRecord:
    """A parsed result bound to verified artifact bytes and its exact dispatch.

    Only the evidence loader should publish this representation. Core consumers
    use its typed record; passive report dictionaries are serialization exports.
    """

    report_json: str
    expectation: ValidationEvidenceExpectation
    evidence: ValidationEvidence
    artifact_bytes: bytes
    record: ValidationRecord = field(init=False)

    def __post_init__(self) -> None:
        """Reject forged or inconsistent typed bindings before publication."""
        if not isinstance(self.expectation, ValidationEvidenceExpectation) or not isinstance(self.evidence, ValidationEvidence):
            msg = "verified validation requires typed record, expectation and evidence"
            raise TypeError(msg)
        record = ValidationRecord.from_raw(json.loads(self.report_json))
        if not isinstance(self.artifact_bytes, bytes) or digest_bytes(self.artifact_bytes) != record.artifact_digest:
            msg = "verified validation artifact bytes differ from the recorded digest"
            raise ValueError(msg)
        if blockers := _validation_native_result_blockers(self.artifact_bytes, self.expectation, self.evidence):
            raise ValueError("validation native evidence failed verification: " + "; ".join(blockers))
        assessment = assess_validation_evidence(self.expectation, self.evidence)
        evidence, expectation = self.evidence, self.expectation
        if assessment.blockers or (
            record.node_id,
            record.evidence_id,
            record.status.value,
            record.source_state,
            record.command_digest,
            record.environment_digest,
            record.artifact_digest,
        ) != (
            evidence.node_id,
            evidence.evidence_id,
            evidence.status,
            evidence.fingerprints.after,
            expectation.command_identity_digest,
            expectation.environment_digest,
            evidence.raw_result_digest,
        ):
            msg = "validation record differs from verified dispatch or execution evidence"
            raise ValueError(msg)
        if (
            record.contract_binding is not None
            and record.source_inputs is not None
            and not record.contract_binding.contract.matches_execution(
                repository_root=Path(record.source_inputs.repository_root),
                commands=expectation.validation_unit.commands,
                working_directories=expectation.validation_unit.working_directories,
            )
        ):
            msg = "validation contract does not match its dispatched execution"
            raise ValueError(msg)
        bind_validation_payload(
            ValidationPayload(record.status, record.executions, record.limitations, record.git_dependencies, record.failure_kind), expectation.validation_unit
        )
        object.__setattr__(self, "record", record)

    def to_document(self) -> dict[str, object]:
        """Serialize passive report data without exposing mutable trusted state."""
        return _object(json.loads(self.report_json), "validation report")

    def applicability_reasons(  # noqa: C901, PLR0911 - distinct source, selection, Git and artifact applicability gates.
        self, target: ReviewSourceSnapshot, *, current_unit: ValidationUnit, observe_artifact: Callable[[ArtifactIdentity], tuple[str, str]]
    ) -> list[dict[str, str]]:
        """Check current applicability once, without parsing or executing again."""
        target.verify()
        record = self.record
        if (validation_command_identity_digest(current_unit), validation_environment_digest(current_unit)) != (
            record.command_digest,
            record.environment_digest,
        ):
            return [
                {
                    "reason_code": "validation-execution-changed",
                    "reason": "Current command, directory, environment or artifact policy differs from the original execution.",
                }
            ]
        if any(head != target.head for head in record.native_ci_heads):
            return [{"reason_code": "native-exact-commit", "reason": "Hosted CI evidence attests to another exact commit."}]
        binding = record.contract_binding
        original = record.source_inputs
        if original is None or binding is None:
            return [
                {"reason_code": "validation-contract-unavailable", "reason": "Reuse requires a repository-owned contract and complete original source inputs."}
            ]
        contract = binding.contract
        if record.limitations or record.status not in {ValidationStatus.PASSED, ValidationStatus.FAILED}:
            return [{"reason_code": "validation-policy", "reason": "Incomplete evidence follows the existing bounded retry policy."}]
        if record.status == ValidationStatus.FAILED and (record.failure_kind != FailureKind.SOURCE or not contract.deterministic):
            return [{"reason_code": "validation-retry", "reason": "Only deterministic contracted source failures are reusable negative evidence."}]
        original_inputs = contract.selected_inputs(original)
        target_inputs = contract.selected_inputs(target)
        if original.repository_root != target.repository_root or original_inputs != target_inputs:
            return [{"reason_code": "validation-inputs-changed", "reason": "Contracted Git input objects, modes, or selection membership changed."}]
        if _unproven_inputs(original_inputs, (*original.repository_symlink_paths, *target.repository_symlink_paths)):
            return [{"reason_code": "validation-inputs-unproven", "reason": "Selected submodule or symlink traversal inputs are not completely proved."}]
        dependencies = set(contract.git_inputs)
        for dependency in record.git_dependencies or ():
            if dependency.kind == GitDependencyKind.INPUT_SELECTION:
                if original.repository_selection_paths is None or original.repository_selection_paths != target.repository_selection_paths:
                    return [{"reason_code": "validation-selection-changed", "reason": "Tracked/nonignored worktree selection changed or is unproven."}]
                continue
            if dependency.kind == GitDependencyKind.SOURCE_DISCOVERY:
                dependencies.update((ContractGitInput.INDEX, ContractGitInput.HEAD))
                continue
            dependencies.add(
                ContractGitInput.INDEX
                if dependency.kind in {GitDependencyKind.INDEX, GitDependencyKind.SOURCE_DISCOVERY}
                else ContractGitInput(dependency.kind.value)
            )
        observed = {
            ContractGitInput.INDEX: (original.index_fingerprint, target.index_fingerprint),
            ContractGitInput.HEAD: (original.head, target.head),
            ContractGitInput.HISTORY: (original.source_state, target.source_state),
            ContractGitInput.COMPARISON: ((original.base_ref, original.merge_base), (target.base_ref, target.merge_base)),
        }
        # Ref-dependent history cannot be established by an unchanged HEAD alone.
        reasons = [
            {"reason_code": "validation-git-input-changed", "reason": f"Declared {kind.value} input changed."}
            for kind in dependencies
            if observed[kind][0] != observed[kind][1]
        ]
        reasons.extend(
            {"reason_code": "validation-artifact-changed", "path": artifact.path, "reason": "Required artifact identity changed or is unavailable."}
            for artifact in record.artifacts
            if observe_artifact(artifact) != (artifact.digest, artifact.digest_mode)
        )
        return reasons

    def historical_source_gate(self, target: ReviewSourceSnapshot) -> bool:
        """Retain a passed scheduling gate without certifying formal metadata reuse."""
        record, origin = self.record, self.record.source_inputs
        if (
            origin is None
            or record.contract_binding is not None
            or record.git_dependencies is None
            or any(dependency.kind != GitDependencyKind.INPUT_SELECTION for dependency in record.git_dependencies)
            or record.limitations
            or record.status != ValidationStatus.PASSED
        ):
            return False
        origin.verify()
        target.verify()
        if Path(target.repository_root, CONTRACT_PATH).exists() or record.native_ci_heads:
            return False
        fields = (
            "repository_root",
            "capture_mode",
            "head",
            "base_ref",
            "merge_base",
            "requested_paths",
            "captured_scope_paths",
            "repository_path_fingerprints",
            "repository_symlink_paths",
        )
        if record.git_dependencies and (origin.repository_selection_paths is None or origin.repository_selection_paths != target.repository_selection_paths):
            return False
        return all(getattr(origin, key) == getattr(target, key) for key in fields) and not _unproven_inputs(
            origin.repository_path_fingerprints, origin.repository_symlink_paths
        )


def _unproven_inputs(inputs: tuple[tuple[str, str], ...], symlink_paths: tuple[str, ...]) -> bool:
    return any(identity.startswith("submodule:") or any(path == link or path.startswith(link + "/") for link in symlink_paths) for path, identity in inputs)


def bind_validation_payload(payload: ValidationPayload, unit: ValidationUnit) -> None:
    """Prove available dispatch constraints before any worker payload write."""
    pairs = tuple((execution.command, execution.working_directory) for execution in payload.executions)
    expected = tuple(zip(unit.commands, unit.working_directories, strict=True))
    if payload.status in {ValidationStatus.PASSED, ValidationStatus.FAILED} and pairs != expected:
        msg = "validation executions require exact dispatched commands and working directories"
        raise ValueError(msg)
    if payload.status == ValidationStatus.BLOCKED and pairs != expected[: len(pairs)]:
        msg = "blocked validation executions must be an ordered dispatch prefix of exact command/directory pairs"
        raise ValueError(msg)
    if unit.dependency_policy == "stop-on-failure":
        stopping_index = next(
            (index for index, execution in enumerate(payload.executions) if execution.result in {ExecutionResult.FAILED, ExecutionResult.BLOCKED}), None
        )
        if stopping_index is not None and any(execution.result != ExecutionResult.NOT_RUN for execution in payload.executions[stopping_index + 1 :]):
            msg = "stop-on-failure validation must record subsequent commands as not-run"
            raise ValueError(msg)
    if unit.dependency_policy == "continue-independent" and any(execution.result == ExecutionResult.NOT_RUN for execution in payload.executions):
        msg = "continue-independent validation cannot skip dispatched command executions"
        raise ValueError(msg)
    if any(execution.executor.strip() == "none" for execution in payload.executions):
        msg = "validation execution requires a concrete executor"
        raise ValueError(msg)
    roots = {artifact.path for artifact in unit.allowed_artifacts}
    approved = {artifact.path: artifact for artifact in unit.allowed_artifacts}
    if any(
        artifact.path not in approved
        or (artifact.kind, artifact.repository_status) != (approved[artifact.path].kind, approved[artifact.path].repository_status)
        for artifact in payload.artifacts
    ):
        msg = "validation reported artifacts must match permitted roots, kinds and repository status"
        raise ValueError(msg)
    invalid_references = sorted({path for execution in payload.executions for path in execution.artifact_paths if path not in roots})
    if invalid_references:
        msg = f"validation execution artifact references must name permitted roots: {sorted(roots)!r}; invalid references: {invalid_references!r}"
        raise ValueError(msg)


def _require_disposition(status: ValidationStatus, executions: tuple[ValidationExecution, ...], limitations: tuple[str, ...]) -> None:
    if status == ValidationStatus.PASSED and (not executions or any(item.result != ExecutionResult.PASSED for item in executions)):
        msg = "passed validation requires passed executions"
        raise ValueError(msg)
    if status == ValidationStatus.FAILED and not any(item.result == ExecutionResult.FAILED for item in executions):
        msg = "failed validation requires a failed execution"
        raise ValueError(msg)
    if status == ValidationStatus.BLOCKED and not limitations:
        msg = "blocked validation requires a limitation"
        raise ValueError(msg)


def _command_requires_git_declaration(command: str) -> bool:
    """Classify complete shell words, retaining uncertainty for invalid quoting."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        words = tuple(lexer)
    except ValueError:
        return True
    return any(word == "HEAD" or word.replace("\\", "/").rsplit("/", 1)[-1] in {"git", "git.exe"} or re.match(r"GIT_[A-Za-z0-9_]*=", word) for word in words)


def _require_git_dependencies(executions: tuple[ValidationExecution, ...], dependencies: tuple[GitDependency, ...] | None) -> None:
    from review_graph_git import _source_discovery_command  # noqa: PLC0415 - same standard Git declaration policy as audits.

    if dependencies is None:
        return
    commands = {execution.command for execution in executions}
    declared: set[str] = set()
    for dependency in dependencies:
        if dependency.command is not None:
            if dependency.command not in commands:
                msg = f"validation Git dependency names an unknown executed command: {dependency.command!r}; copy an exact executions[].command"
                raise ValueError(msg)
            if dependency.command in declared:
                msg = (
                    f"validation Git dependency has a duplicate command binding: {dependency.command!r}; "
                    "bind one dependency to the command and omit command on additional unit-wide dependencies, "
                    "for example command-bound head plus command-less index; correct metadata without rerunning commands"
                )
                raise ValueError(msg)
            declared.add(dependency.command)
        if dependency.kind == GitDependencyKind.SOURCE_DISCOVERY and (dependency.command is None or not _source_discovery_command(dependency.command)):
            msg = "validation source discovery requires a plain local Git diff"
            raise ValueError(msg)
        if dependency.kind == GitDependencyKind.INPUT_SELECTION and dependency.command is not None and _command_requires_git_declaration(dependency.command):
            words = shlex.split(dependency.command)
            if len(words) != 6 or words[:2] != ["git", "ls-files"] or set(words[2:]) != {"--cached", "--others", "--exclude-standard", "-z"}:
                msg = (
                    "input-selection supports only plain git ls-files --cached --others --exclude-standard -z; staged blobs, HEAD and history stay conservative"
                )
                raise ValueError(msg)
    if any(_command_requires_git_declaration(command) and command not in declared for command in commands):
        msg = "source-only validation cannot execute an unclassified Git command"
        raise ValueError(msg)
