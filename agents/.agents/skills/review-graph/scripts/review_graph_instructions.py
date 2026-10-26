"""Required guidance inventory and bounded delivery, never a read attestation."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from review_graph_integrity import canonical_json, digest_bytes
from review_graph_read_provenance import file_identity
from review_graph_session import runtime_command

CHUNK_BYTES = 16 * 1024
LARGE_CORPUS_BYTES = 128 * 1024
RELOAD_POLICY = (
    "On fresh context, compaction, or lost guidance, load every required file before work. "
    "The manifest supplies bounded full-text chunks and immutable originals; read all chunks without truncation. "
    "A disk snapshot, digest, prior receipt, or summary does not attest current model availability or comprehension. "
    "Retain applicable obligations while inspecting bounded source units; if the mandatory corpus cannot fit, "
    "report the context limitation and obtain a consumer-authorized execution view before proceeding."
)


class InstructionChunkOutOfRangeError(ValueError):
    """The instruction identities are valid but the requested chunk is absent."""


def _content(path: str) -> bytes:
    identity = file_identity(path)
    content = Path(path).read_bytes()
    if digest_bytes(content) != identity:
        msg = f"instruction changed during inventory: {path}"
        raise ValueError(msg)
    return content


def _chunks(content: bytes) -> list[list[int]]:
    # UTF-8 boundaries also bound a single very long line without losing bytes.
    content.decode("utf-8")
    chunks = []
    start = 0
    while start < len(content):
        end = min(start + CHUNK_BYTES, len(content))
        while end < len(content) and content[end] & 0xC0 == 0x80:
            end -= 1
        chunks.append([start, end])
        start = end
    return chunks


def instruction_context(paths: tuple[str, ...], store: Path) -> tuple[dict[str, Any], dict[Path, bytes]]:
    """Snapshot the complete declared corpus without selecting or summarizing rules."""
    files: list[dict[str, Any]] = []
    writes = {}
    for path in sorted(set(paths)):
        content = _content(path)
        digest = digest_bytes(content)
        snapshot = store / f"instruction-text.{digest[7:]}.txt"
        writes[snapshot] = content
        files.append(
            {
                "path": path,
                "digest": digest,
                "snapshot_path": str(snapshot),
                "bytes": len(content),
                "lines": len(content.splitlines()),
                "chunks": _chunks(content),
            }
        )
    manifest = {"schema_version": 1, "files": files, "chunk_bytes": CHUNK_BYTES, "reload_policy": RELOAD_POLICY}
    content = (canonical_json(manifest) + "\n").encode()
    digest = digest_bytes(content)
    path = store / f"instruction-corpus.{digest[7:]}.json"
    writes[path] = content
    return {
        "manifest": {"path": str(path), "digest": digest},
        "file_count": len(files),
        "bytes": sum(item["bytes"] for item in files),
        "lines": sum(item["lines"] for item in files),
        "model_availability": "unknown",
        "read_command": runtime_command(Path(__file__), "--manifest", str(path), "--digest", digest),
        "read_arguments": "Append --path <original instruction path> --chunk <zero-based index> for every chunk of every file.",
        "reload_policy": RELOAD_POLICY,
    }, writes


def load_manifest(manifest_path: Path, digest: str) -> dict[str, Any]:
    """Parse only the exact generated manifest bound by the dispatch."""
    content = _content(str(manifest_path))
    if digest_bytes(content) != digest:
        msg = "instruction manifest digest mismatch"
        raise ValueError(msg)
    return json.loads(content)


def read_chunk(manifest_path: Path, digest: str, path: str, chunk: int) -> bytes:
    """Return exact text only after verifying the manifest, snapshot and live identity."""
    return read_manifest_chunk(load_manifest(manifest_path, digest), path, chunk)


def read_manifest_chunk(manifest: dict[str, Any], path: str, chunk: int) -> bytes:
    """Read from a validated manifest, checking file identities before the chunk index."""
    record = next((item for item in manifest["files"] if item["path"] == path), None)
    if record is None:
        msg = "instruction file or chunk is not in the bound manifest"
        raise ValueError(msg)
    snapshot = _content(record["snapshot_path"])
    if digest_bytes(snapshot) != record["digest"] or file_identity(path) != record["digest"]:
        msg = "required instruction identity changed; recapture and replan"
        raise ValueError(msg)
    if not 0 <= chunk < len(record["chunks"]):
        msg = "instruction chunk is not in the bound manifest"
        raise InstructionChunkOutOfRangeError(msg)
    start, end = record["chunks"][chunk]
    return snapshot[start:end]


def read_demand(path_sets: list[list[str]], *, strict: bool = True) -> dict[str, Any]:
    """Count bytes by path and consumer; these are planned reads, not token usage."""
    counts = Counter(path for paths in path_sets for path in set(paths))
    files: list[dict[str, Any]] = []
    for path, count in sorted(counts.items()):
        content = _content(path) if strict else Path(path).read_bytes()
        files.append({"path": path, "digest": digest_bytes(content), "bytes": len(content), "lines": len(content.splitlines()), "planned_reads": count})
    sizes = {item["path"]: item["bytes"] for item in files}
    unique = sum(sizes.values())
    planned = sum(item["bytes"] * item["planned_reads"] for item in files)
    return {
        "unique_bytes": unique,
        "planned_bytes": planned,
        "repeated_bytes": planned - unique,
        "max_bytes_per_node": max((sum(sizes[path] for path in set(paths)) for paths in path_sets), default=0),
        "planned_file_reads": sum(counts.values()),
        "unique_files": len(files),
        "files": files,
        "observed_model_reads": None,
        "provider_tokens": None,
        "model_review_seconds": None,
    }


def instruction_preflight(demand: dict[str, Any]) -> dict[str, Any]:
    """Keep oversized corpora visible in the default pre-fanout receipt."""
    return {
        **{key: value for key, value in demand.items() if key != "files"},
        "large_corpus": demand["max_bytes_per_node"] >= LARGE_CORPUS_BYTES,
        "diagnostic_threshold_bytes": LARGE_CORPUS_BYTES,
        "largest_files": sorted(demand["files"], key=lambda item: (-item["bytes"], item["path"]))[:3],
        "measurement_scope": "File bytes and planned delivery only; not context capacity, provider tokens, latency, savings, or review equivalence.",
        "reload_policy": RELOAD_POLICY,
    }


def main() -> None:
    """Emit one verified chunk without creating a read receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--chunk", type=int, required=True)
    args = parser.parse_args()
    sys.stdout.buffer.write(read_chunk(args.manifest, args.digest, args.path, args.chunk))


if __name__ == "__main__":
    main()
