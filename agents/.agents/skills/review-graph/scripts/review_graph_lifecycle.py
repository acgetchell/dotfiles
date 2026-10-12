"""Bound source repairs and retain explicit stopping and restart decisions."""

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

_EXTENSION_ERROR = "repair budget extensions require a positive increment and explicit user authorization"
_RESTART_ERROR = "comprehensive restart requires a concrete trigger, its evidence, and why targeted verification is insufficient"


def _substantive_text(value: object) -> bool:
    """Check raw constructor values without trusting their annotations."""
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True, slots=True)
class ControlReference:
    """An immutable runtime-issued control artifact reference."""

    path: str
    digest: str

    def __post_init__(self) -> None:
        """Keep transport references absolute and content-bound."""
        if (
            not _substantive_text(self.path)
            or not Path(self.path).is_absolute()
            or not isinstance(self.digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", self.digest) is None
        ):
            msg = "run control references require an absolute path and SHA-256 digest"
            raise ValueError(msg)

    @classmethod
    def from_document(cls, raw: Any) -> ControlReference:
        """Detach the two reference scalars from transport input."""
        if not isinstance(raw, dict) or set(raw) != {"path", "digest"}:
            msg = "run control reference requires path and digest"
            raise ValueError(msg)
        return cls(raw["path"], raw["digest"])


@dataclass(frozen=True, slots=True)
class RunControlBinding:
    """A shared run identity and the budget generation retained by every plan."""

    identity: ControlReference
    generation: ControlReference

    def __post_init__(self) -> None:
        """Reject mutable or unparsed nested references."""
        if not isinstance(self.identity, ControlReference) or not isinstance(self.generation, ControlReference):
            msg = "run control binding requires immutable control references"
            raise TypeError(msg)

    @classmethod
    def from_document(cls, raw: Any) -> RunControlBinding:
        """Parse and detach the shared control references."""
        if not isinstance(raw, dict) or set(raw) != {"identity", "generation"}:
            msg = "run control binding requires identity and generation"
            raise ValueError(msg)
        return cls(ControlReference.from_document(raw["identity"]), ControlReference.from_document(raw["generation"]))


@dataclass(frozen=True, slots=True)
class RepairBudgetExtension:
    """One immutable, explicitly authorized increase to the repair budget."""

    additional_epochs: int
    user_authorization: str

    def __post_init__(self) -> None:
        """Reject invalid authorization or increments before creating history."""
        if type(self.additional_epochs) is not int or self.additional_epochs < 1 or not _substantive_text(self.user_authorization):
            raise ValueError(_EXTENSION_ERROR)

    @classmethod
    def from_document(cls, raw: Any) -> RepairBudgetExtension:
        """Detach validated scalar values from a transport dictionary."""
        if not isinstance(raw, dict) or set(raw) != {"additional_epochs", "user_authorization"}:
            raise ValueError(_EXTENSION_ERROR)
        return cls(raw["additional_epochs"], raw["user_authorization"])


@dataclass(frozen=True, slots=True)
class ComprehensiveRestart:
    """One immutable explanation for restarting a comprehensive review."""

    trigger: Literal["confirmed-new-defect", "expanded-source-scope", "explicit-user-request"]
    evidence: str
    targeted_verification_insufficient: str

    def __post_init__(self) -> None:
        """Keep every stored restart category and explanation substantive."""
        if any(not _substantive_text(value) for value in (self.trigger, self.evidence, self.targeted_verification_insufficient)) or self.trigger not in {
            "confirmed-new-defect",
            "expanded-source-scope",
            "explicit-user-request",
        }:
            raise ValueError(_RESTART_ERROR)

    @classmethod
    def from_document(cls, raw: Any) -> ComprehensiveRestart:
        """Parse the restart category and detach its evidence from raw input."""
        if not isinstance(raw, dict) or set(raw) != {"trigger", "evidence", "targeted_verification_insufficient"}:
            raise ValueError(_RESTART_ERROR)
        return cls(raw["trigger"], raw["evidence"], raw["targeted_verification_insufficient"])


@dataclass(frozen=True)
class ReviewLifecycle:
    """Run-wide limits survive replanning, scheduling, and commit handoffs."""

    repair_budget: int = 2
    repairs_completed: int = 0
    budget_extensions: tuple[RepairBudgetExtension, ...] = ()
    comprehensive_restarts: tuple[ComprehensiveRestart, ...] = ()
    stop_reason: str | None = None
    run_control: RunControlBinding | None = None

    def next_repair(self, ordinal: int) -> ReviewLifecycle:
        """Count one content-changing batch, including optional fixes and formatting."""
        self.require_active()
        if type(ordinal) is not int or ordinal != self.repairs_completed + 1:
            msg = "repair_epoch must be the next consecutive run-wide ordinal"
            raise ValueError(msg)
        if ordinal > self.repair_budget:
            msg = "repair budget exhausted; explicit user budget extension required"
            raise ValueError(msg)
        return replace(self, repairs_completed=ordinal)

    def require_active(self) -> None:
        """A stopped run cannot launch work or silently restart."""
        if self.stop_reason is not None:
            raise ValueError(f"review stopped: {self.stop_reason}")


def lifecycle_from_document(raw: Any) -> ReviewLifecycle:
    """Validate durable control state without coercing counters or authorization."""
    if raw is None:
        return ReviewLifecycle()
    fields = set(ReviewLifecycle.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) not in (fields, fields - {"run_control"}):
        msg = "review_lifecycle requires the complete lifecycle fields"
        raise ValueError(msg)
    budget, completed = raw["repair_budget"], raw["repairs_completed"]
    if type(budget) is not int or type(completed) is not int or not 0 <= completed <= budget:
        msg = "review_lifecycle requires nonnegative counters within the repair budget"
        raise ValueError(msg)
    extensions = raw["budget_extensions"]
    restarts = raw["comprehensive_restarts"]
    if not isinstance(extensions, (list, tuple)) or not isinstance(restarts, (list, tuple)):
        msg = "review_lifecycle history must be arrays"
        raise TypeError(msg)
    parsed_extensions = tuple(RepairBudgetExtension.from_document(entry) for entry in extensions)
    expected_budget = 2 + sum(entry.additional_epochs for entry in parsed_extensions)
    if budget != expected_budget:
        msg = "repair budget differs from its explicit extension history"
        raise ValueError(msg)
    parsed_restarts = tuple(ComprehensiveRestart.from_document(entry) for entry in restarts)
    reason = raw["stop_reason"]
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        msg = "stop_reason must be null or substantive text"
        raise ValueError(msg)
    binding = RunControlBinding.from_document(raw["run_control"]) if raw.get("run_control") is not None else None
    return ReviewLifecycle(budget, completed, parsed_extensions, parsed_restarts, reason, binding)
