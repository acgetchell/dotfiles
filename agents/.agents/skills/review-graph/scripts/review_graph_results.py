"""Strict JSON input and typed recovery decisions shared by every review worker."""

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, TypedDict

from review_graph_schema import SchemaValidationError, require_schema_definition

OUTCOME_SCHEMA = Path(__file__).resolve().parents[1] / "references" / "schemas" / "review-outcome-v1.schema.json"


class RejectionKind(StrEnum):
    """Machine categories distinguish absent evidence from valid negative findings."""

    MISSING_INPUT = "missing-required-input"
    MALFORMED_INPUT = "malformed-input"
    MISSING_EVIDENCE = "missing-evidence"
    STALE_CAPTURE = "stale-capture"
    UNSUPPORTED_TRANSITION = "unsupported-transition"
    UNCLASSIFIED = "unclassified-failure"


class RecoveryKind(StrEnum):
    """Prerequisites to reconsidering one failed evaluation, never automatic loops."""

    SUPPLY_INPUT = "supply-required-input"
    CORRECT_INPUT = "correct-input"
    OBTAIN_EVIDENCE = "obtain-evidence"
    RECAPTURE = "recapture-source"
    RECONCILE = "reconcile-transition"
    INSPECT = "inspect-blocker"


class EvaluationBoundaryError(ValueError):
    """A known boundary failure with a category callers can handle exhaustively."""

    def __init__(self, kind: RejectionKind, message: str) -> None:
        """Reject unknown categories instead of widening them into retryable errors."""
        if not isinstance(kind, RejectionKind):
            msg = "evaluation boundary error requires a typed rejection kind"
            raise TypeError(msg)
        self.kind = kind
        super().__init__(message)


class RecoveryPayload(TypedDict, closed=True):
    """The shared recovery wire contract; unknown prerequisites never authorize retries."""

    kind: RecoveryKind
    scope: Literal["affected-evaluation"]
    automatic_retry: Literal[False]


class RejectionPayload(TypedDict, closed=True):
    """A rejected evaluation has no accepted evidence or negative applicability claim."""

    kind: RejectionKind
    accepted: Literal[False]
    recovery: RecoveryPayload


@dataclass(frozen=True, slots=True)
class EvaluationRejection:
    """Parse exception types into recovery policy without matching diagnostic prose."""

    kind: RejectionKind

    def __post_init__(self) -> None:
        """Preserve the closed category after construction."""
        if not isinstance(self.kind, RejectionKind):
            msg = "evaluation rejection requires a typed kind"
            raise TypeError(msg)

    @classmethod
    def from_exception(cls, error: Exception) -> EvaluationRejection:
        """Unknown semantic failures stay blocked until inspected."""
        if isinstance(error, EvaluationBoundaryError):
            return cls(error.kind)
        if isinstance(error, SchemaValidationError):
            return cls(RejectionKind.MISSING_INPUT if any(item.code == "required" for item in error.diagnostics) else RejectionKind.MALFORMED_INPUT)
        if isinstance(error, (json.JSONDecodeError, UnicodeError)):
            return cls(RejectionKind.MALFORMED_INPUT)
        return cls(RejectionKind.UNCLASSIFIED)

    @classmethod
    def from_document(cls, raw: object) -> EvaluationRejection:
        """Reject missing fields, unknown variants and contradictory recovery claims."""
        require_schema_definition(raw, OUTCOME_SCHEMA, "rejection")
        if not isinstance(raw, dict):
            msg = "rejection must be an object"
            raise TypeError(msg)
        return cls(RejectionKind(raw["kind"]))

    def as_dict(self) -> RejectionPayload:
        """Serialize one deterministic prerequisite; success remains compiler-owned."""
        actions = {
            RejectionKind.MISSING_INPUT: RecoveryKind.SUPPLY_INPUT,
            RejectionKind.MALFORMED_INPUT: RecoveryKind.CORRECT_INPUT,
            RejectionKind.MISSING_EVIDENCE: RecoveryKind.OBTAIN_EVIDENCE,
            RejectionKind.STALE_CAPTURE: RecoveryKind.RECAPTURE,
            RejectionKind.UNSUPPORTED_TRANSITION: RecoveryKind.RECONCILE,
            RejectionKind.UNCLASSIFIED: RecoveryKind.INSPECT,
        }
        return {"kind": self.kind, "accepted": False, "recovery": {"kind": actions[self.kind], "scope": "affected-evaluation", "automatic_retry": False}}


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        seen: set[str] = set()
        for key, _value in pairs:
            if key in seen:
                raise EvaluationBoundaryError(RejectionKind.MALFORMED_INPUT, f"JSON object contains duplicate field {key!r}")
            seen.add(key)
    return result


def _reject_nonfinite(value: object) -> None:
    """Locate a complete field path only on the malformed-number error path."""
    pending = [(value, "$")]
    while pending:
        item, path = pending.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise EvaluationBoundaryError(RejectionKind.MALFORMED_INPUT, f"{path}: JSON does not permit nonfinite numbers")
        if isinstance(item, list):
            pending.extend((child, f"{path}[{index}]") for index, child in enumerate(item))
        elif isinstance(item, dict):
            pending.extend((child, f"{path}.{key}" if key.isidentifier() else f"{path}[{json.dumps(key)}]") for key, child in item.items())


def parse_json_object(content: str | bytes) -> dict[str, Any]:
    """Decode transport strictly; callers then apply their schema and domain parser."""
    nonfinite = False

    def number(raw: str) -> float:
        nonlocal nonfinite
        value = float(raw)
        nonfinite = nonfinite or not math.isfinite(value)
        return value

    try:
        value = json.loads(content, object_pairs_hook=_object_pairs, parse_float=number, parse_constant=number)
    except EvaluationBoundaryError:
        raise
    except (ValueError, RecursionError, UnicodeError) as error:
        raise EvaluationBoundaryError(RejectionKind.MALFORMED_INPUT, str(error)) from error
    if not isinstance(value, dict):
        raise EvaluationBoundaryError(RejectionKind.MALFORMED_INPUT, "input root must be a JSON object")
    if nonfinite:
        _reject_nonfinite(value)
    return value
