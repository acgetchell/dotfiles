"""Deterministic dispatch cost projections, separate from observed worker work."""

from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def projected_waves(nodes: list[dict[str, Any]], concurrent_worker_limit: int) -> list[list[str]]:
    """Schedule unit-duration waves without dropping dependencies or serial validators."""
    if isinstance(concurrent_worker_limit, bool) or not isinstance(concurrent_worker_limit, int) or concurrent_worker_limit < 1:
        msg = "concurrent_worker_limit must be a positive integer"
        raise ValueError(msg)
    remaining = {node["node_id"]: node for node in nodes}
    completed: set[str] = set()
    waves: list[list[str]] = []
    while remaining:
        ready = [node for node in remaining.values() if set(node["predecessors"]) <= completed]
        # Validation/fix work shares the repository mutation boundary.
        serial = next((node for node in ready if node["mode"] in {"validation", "fix"}), None)
        wave = [serial["node_id"]] if serial else [node["node_id"] for node in ready[:concurrent_worker_limit]]
        if not wave:
            msg = "cannot project waves with missing or cyclic dependencies"
            raise ValueError(msg)
        waves.append(wave)
        completed.update(wave)
        for node_id in wave:
            del remaining[node_id]
    return waves


def source_demand(nodes: list[dict[str, Any]], repository_root: Path) -> dict[str, Any]:
    """Count planned audit/independent reads; never describe them as observed reads."""
    counts = Counter(path for node in nodes if node["mode"] in {"audit", "independent-review"} for path in node["coverage"])
    sizes: dict[str, int] = {}
    unavailable: list[str] = []
    for path in counts:
        candidate = (repository_root / path).resolve()
        try:
            if not candidate.is_relative_to(repository_root) or not candidate.is_file():
                unavailable.append(path)
                continue
            sizes[path] = candidate.stat().st_size
        except OSError:
            unavailable.append(path)
    return {
        "planned_file_reads": sum(counts.values()),
        "distinct_paths": len(counts),
        "repeated_file_reads": sum(counts.values()) - len(counts),
        "planned_source_bytes": sum(counts[path] * size for path, size in sizes.items()),
        "distinct_source_bytes": sum(sizes.values()),
        "overlapping_paths": {path: count for path, count in sorted(counts.items()) if count > 1},
        "unavailable_paths": sorted(unavailable),
    }
