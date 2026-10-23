"""Typed machine actions and limitations at the repair continuation boundary."""

from dataclasses import dataclass, field
from typing import Literal

from review_graph_results import OUTCOME_SCHEMA
from review_graph_schema import require_schema_definition


def _valid_command(raw: object) -> bool:
    return isinstance(raw, tuple) and bool(raw) and all(isinstance(word, str) and bool(word) and "\0" not in word for word in raw)


@dataclass(frozen=True, slots=True)
class NextReadyAction:
    """Discover pending work using the published, source-bound continuation."""

    command: tuple[str, ...]
    kind: Literal["continue-review"] = field(default="continue-review", init=False)
    operation: Literal["next-ready"] = field(default="next-ready", init=False)

    def __post_init__(self) -> None:
        """An action must contain an executable command, never an empty hint."""
        if not _valid_command(self.command):
            msg = "next-ready action requires an immutable command argument vector"
            raise ValueError(msg)

    @classmethod
    def from_document(cls, raw: object) -> NextReadyAction:
        """Parse only this known action; transport data never selects arbitrary kinds."""
        require_schema_definition(raw, OUTCOME_SCHEMA, "next-ready")
        if not isinstance(raw, dict):
            msg = "next-ready action must be an object"
            raise TypeError(msg)
        return cls(tuple(raw["command"]))


@dataclass(frozen=True, slots=True)
class MissingIntermediateCapture:
    """Endpoint proof cannot establish the unobserved history between captures."""

    kind: Literal["missing-intermediate-capture"] = field(default="missing-intermediate-capture", init=False)
    message: str = field(
        default="No post-repair/pre-staging capture exists. Endpoint evidence does not establish intermediate source/index states or edit/staging order.",
        init=False,
    )
