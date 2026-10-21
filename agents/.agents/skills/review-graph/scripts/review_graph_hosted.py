"""Report hosted results separately from coverage of the delivered source."""

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from capture_scope import _committed_gitlink, _committed_tree, _run_git
from research_repo_tools.process import ExecutableNotFoundError

if TYPE_CHECKING:
    from review_graph_reuse import ReviewSourceSnapshot


def _matches_committed_source(git: str, snapshot: ReviewSourceSnapshot, tree_id: str) -> bool:
    """Compare opaque gitlinks against clean committed identities when needed."""
    if snapshot.git_tree_id is not None:
        return snapshot.git_tree_id == tree_id
    repository = Path(snapshot.repository_root)
    committed = {
        path: _committed_gitlink(git, repository, path, identity)[0] if identity.mode == "160000" else identity.serialize()
        for path, identity in _committed_tree(git, repository, snapshot.head).items()
    }
    return committed == {path: identity for path, identity in snapshot.repository_path_fingerprints if identity != "absent"}


def hosted_coverage(record: dict[str, Any], snapshot: ReviewSourceSnapshot | None) -> dict[str, Any]:
    """Bind observed commits to immutable trees, never to an observer's host."""
    results = record.get("native_ci", [])
    heads = sorted({item["head_sha"] for item in results})
    identities = []
    covers_current = False
    if snapshot is not None:
        snapshot.verify()
        git = shutil.which("git")
        if git is not None:
            for head in heads:
                if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head) is None:
                    continue
                try:
                    tree = _run_git(git, Path(snapshot.repository_root), ("rev-parse", "--verify", head + "^{tree}")).decode().strip()
                except ExecutableNotFoundError, OSError, RuntimeError:
                    continue
                algorithm = "sha1" if len(head) == 40 else "sha256"
                identities.append({"head_sha": head, "git_tree_id": f"git:{algorithm}:tree:{tree}"})
            if heads == [snapshot.head] and len(identities) == 1:
                try:
                    covers_current = _matches_committed_source(git, snapshot, identities[0]["git_tree_id"])
                except ExecutableNotFoundError, OSError, RuntimeError:
                    covers_current = False  # Unavailable committed identities cannot establish coverage.
    succeeded = all(item["conclusion"] == "success" for item in results) and record.get("status") in {"passed", "reused"}
    next_action = None if succeeded else "Diagnose the failed hosted results for the current source."
    if not covers_current:
        next_action = "Obtain matching hosted results; dirty repairs require an authorized commit handoff."
    return {
        "observed_head_shas": heads,
        "tested_targets": sorted({item["target"] for item in results}),
        "results": results,
        "limitations": record.get("limitations", []),
        "covered_source_identity": identities,
        "delivered_source_state": list(snapshot.source_state) if snapshot is not None else None,
        "coverage_status": "current-source" if covers_current else "committed-baseline-only" if identities else "unverified",
        "delivered_source_status": ("passed" if succeeded else "failed") if covers_current else "pending",
        "next_action": next_action,
    }
