"""Observe external content changes without modifying their capture evidence."""

import shutil
from pathlib import Path
from typing import Any

from capture_scope import _scope_data
from review_graph_results import EvaluationBoundaryError, RejectionKind
from review_graph_reuse import source_snapshot


def verify_live_source(capture: dict[str, Any]) -> None:
    """Reject edits after the supplied capture before publishing a continuation."""
    expected = source_snapshot(capture)
    expected.verify()
    git = shutil.which("git")
    if git is None:
        msg = "external source continuation requires Git for a live capture"
        raise ValueError(msg)
    try:
        current = _scope_data(git, Path(expected.repository_root), expected.capture_mode, expected.base_ref, expected.requested_paths)
    except RuntimeError as error:
        msg = f"live source capture failed during external reconciliation; recapture the actual state: {error}"
        raise EvaluationBoundaryError(RejectionKind.STALE_CAPTURE, msg) from error
    if source_snapshot(current) != expected or current["captured_path_line_bounds"] != capture.get("captured_path_line_bounds"):
        msg = "source changed during external reconciliation; retain the attempts and recapture the actual state"
        raise EvaluationBoundaryError(RejectionKind.STALE_CAPTURE, msg)
