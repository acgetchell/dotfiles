"""Bound source repairs and retain explicit stopping and restart decisions."""

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class ReviewLifecycle:
    """Run-wide limits survive replanning, scheduling, and commit handoffs."""

    repair_budget: int = 2
    repairs_completed: int = 0
    budget_extensions: tuple[dict[str, Any], ...] = ()
    comprehensive_restarts: tuple[dict[str, str], ...] = ()
    stop_reason: str | None = None

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
    if not isinstance(raw, dict) or set(raw) != set(ReviewLifecycle.__dataclass_fields__):
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
    expected_budget = 2
    for entry in extensions:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"additional_epochs", "user_authorization"}
            or type(entry["additional_epochs"]) is not int
            or entry["additional_epochs"] < 1
            or not isinstance(entry["user_authorization"], str)
            or not entry["user_authorization"].strip()
        ):
            msg = "repair budget extensions require a positive increment and explicit user authorization"
            raise ValueError(msg)
        expected_budget += entry["additional_epochs"]
    if budget != expected_budget:
        msg = "repair budget differs from its explicit extension history"
        raise ValueError(msg)
    for entry in restarts:
        validate_restart(entry)
    reason = raw["stop_reason"]
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        msg = "stop_reason must be null or substantive text"
        raise ValueError(msg)
    return ReviewLifecycle(budget, completed, tuple(extensions), tuple(restarts), reason)


def validate_restart(entry: Any) -> None:
    """Pending CI or unfinished proof bookkeeping cannot authorize a new full pass."""
    if (
        not isinstance(entry, dict)
        or set(entry) != {"trigger", "evidence", "targeted_verification_insufficient"}
        or entry["trigger"] not in {"confirmed-new-defect", "expanded-source-scope", "explicit-user-request"}
        or any(not isinstance(value, str) or not value.strip() for value in entry.values())
    ):
        msg = "comprehensive restart requires a concrete trigger, its evidence, and why targeted verification is insufficient"
        raise ValueError(msg)
