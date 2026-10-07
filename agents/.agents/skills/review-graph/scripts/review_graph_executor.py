"""Explicit executor permissions within the existing digest-bound feature identity."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

PERMISSION_FEATURE = "executor-permissions="
PERMISSIONS = frozenset({"use_default", "require_escalated"})


def executor_permissions(features: Sequence[str]) -> str:
    """Parse the reserved feature once; legacy units use the default executor."""
    declarations = [feature.removeprefix(PERMISSION_FEATURE) for feature in features if feature.startswith(PERMISSION_FEATURE)]
    if len(declarations) > 1 or any(value not in PERMISSIONS for value in declarations):
        msg = "validation features require at most one executor-permissions=use_default|require_escalated declaration"
        raise ValueError(msg)
    return declarations[0] if declarations else "use_default"


def remedied_features(features: Sequence[str], permissions: str) -> tuple[str, ...]:
    """Keep unrelated features and bind a replacement's required permission mode."""
    if permissions not in PERMISSIONS:
        msg = "unknown executor permission mode"
        raise ValueError(msg)
    return tuple(sorted([*(feature for feature in features if not feature.startswith(PERMISSION_FEATURE)), PERMISSION_FEATURE + permissions]))
