"""Report hosted results separately from coverage of the delivered source."""

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from capture_scope import _run_git
from research_repo_tools.process import ExecutableNotFoundError

if TYPE_CHECKING:
    from review_graph_reuse import ReviewSourceSnapshot


def hosted_coverage(record: dict[str, Any], snapshot: ReviewSourceSnapshot | None) -> dict[str, Any]:
    """Bind observed commits to immutable trees, never to an observer's host."""
    results = record.get("native_ci", [])
    heads = sorted({item["head_sha"] for item in results})
    identities = []
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
    matches = (
        snapshot is not None
        and heads == [snapshot.head]
        and len(identities) == 1
        and identities[0]["git_tree_id"] == snapshot.git_tree_id
        and all(item["conclusion"] == "success" for item in results)
        and record.get("status") in {"passed", "reused"}
    )
    return {
        "observed_head_shas": heads,
        "tested_targets": sorted({item["target"] for item in results}),
        "results": results,
        "limitations": record.get("limitations", []),
        "covered_source_identity": identities,
        "delivered_source_state": list(snapshot.source_state) if snapshot is not None else None,
        "coverage_status": "current-source" if matches else "committed-baseline-only" if identities else "unverified",
        "delivered_source_status": "passed" if matches else "pending",
        "next_action": None if matches else "Obtain matching hosted results; dirty repairs require an authorized commit handoff.",
    }
