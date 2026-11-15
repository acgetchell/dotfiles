"""Discover paths in a bound capture, without consulting live files or rg configuration."""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from review_graph_handoffs import _literal_words
from review_graph_integrity import digest_bytes
from review_graph_session import runtime_command, verify_current_snapshot

if TYPE_CHECKING:
    from review_graph_reuse import ReviewSourceSnapshot


@dataclass(frozen=True)
class SourceDiscovery:
    """A literal selection query and the complete path membership it observed."""

    paths: tuple[str, ...]
    globs: tuple[str, ...]
    selected_paths: tuple[str, ...]

    @classmethod
    def parse(cls, raw: Any) -> SourceDiscovery:
        """Reject unknown fields and malformed saved selection dependencies."""
        if not isinstance(raw, dict) or set(raw) != {"paths", "globs", "selected_paths"}:
            msg = "source discovery requires paths, globs, and selected_paths"
            raise ValueError(msg)
        if any(not isinstance(value, (tuple, list)) or any(not isinstance(item, str) or not item for item in value) for value in raw.values()):
            msg = "source discovery fields must be arrays of nonempty strings"
            raise ValueError(msg)
        result = cls(*(tuple(raw[key]) for key in ("paths", "globs", "selected_paths")))
        result.verify()
        return result

    def verify(self) -> None:
        """Keep roots literal, relative and canonical; globs use fnmatchcase semantics."""
        if not self.paths or any(
            (path != "." and (PurePosixPath(path).is_absolute() or PurePosixPath(path).as_posix() != path or ".." in path.split("/")))
            or any(character in path for character in "\\\0*?[")
            for path in self.paths
        ):
            msg = "source discovery paths must be literal canonical repository-relative paths (or '.')"
            raise ValueError(msg)
        if any(not pattern or "\0" in pattern or "\\" in pattern for pattern in self.globs):
            msg = "source discovery globs must be nonempty NUL-free POSIX patterns"
            raise ValueError(msg)
        if self.selected_paths != tuple(sorted(set(self.selected_paths))):
            msg = "source discovery requires sorted unique selected paths"
            raise ValueError(msg)

    def select(self, snapshot: ReviewSourceSnapshot) -> tuple[str, ...]:
        """Select only captured tracked/nonignored membership, including empty results."""
        self.verify()
        snapshot.verify()
        universe = snapshot.repository_selection_paths
        if universe is None:
            msg = "source discovery requires a capture with tracked/nonignored selection; recapture before starting a new run"
            raise ValueError(msg)
        return tuple(
            path
            for path in universe
            if any(root in (".", path) or path.startswith(root + "/") for root in self.paths)
            and (not self.globs or any(fnmatchcase(path, pattern) for pattern in self.globs))
        )

    def verify_reuse(self, origin: ReviewSourceSnapshot, target: ReviewSourceSnapshot) -> None:
        """Reject added or removed matches even when all previously read files survive."""
        if self.select(origin) != self.selected_paths or self.select(target) != self.selected_paths:
            msg = "audit reuse source discovery selection changed"
            raise ValueError(msg)


def discovery_context(dispatch: dict[str, Any]) -> dict[str, Any] | None:
    """Supply the bound command before workers choose discovery operations."""
    before = dispatch.get("audit_observations", {}).get("before")
    if before is None:
        return None
    return {
        "command": runtime_command(Path(__file__), "--capture", before["capture_path"], "--source-state", ",".join(dispatch["source_state"])),
        "capture_path": before["capture_path"],
        "policy": (
            "Run audit_observations.before.capture_command first. Append --path <literal repository-relative root> (repeatable) "
            "and optional --glob <quoted pattern> (repeatable, OR). Defaults to all captured tracked/nonignored paths. "
            "Patterns match the whole POSIX path with case-sensitive fnmatchcase; '*' can cross '/'. "
            "The output lists paths only, not inspected content. Live rg --files, ignore/config files and arbitrary shell compounds remain unclassified."
        ),
    }


def load_discovery(capture: Path, state: tuple[str, ...], paths: tuple[str, ...], globs: tuple[str, ...]) -> tuple[SourceDiscovery, str]:
    """Validate the captured source identity and return exact selection inputs."""
    from review_graph_read_provenance import file_identity  # noqa: PLC0415 - shared no-symlink identity, cyclic only at module initialization.
    from review_graph_reuse import source_snapshot  # noqa: PLC0415 - source identity also stores discovery dependencies.

    digest = file_identity(str(capture))
    content = capture.read_bytes()
    if digest_bytes(content) != digest:
        msg = "source discovery capture changed while reading"
        raise ValueError(msg)
    snapshot = source_snapshot(json.loads(content))
    snapshot.verify()
    if snapshot.source_state != state:
        msg = "source discovery capture differs from the dispatched source state"
        raise ValueError(msg)
    query = SourceDiscovery(paths or (".",), globs, ())
    return SourceDiscovery(query.paths, query.globs, query.select(snapshot)), digest


def bind_discovery(command: str, dispatch: dict[str, Any]) -> tuple[SourceDiscovery, tuple[str, str]] | None:
    """Classify only the generated command with the supported literal selectors."""
    context = dispatch.get("source_discovery")
    if context is None:
        return None
    try:
        words = _literal_words(command)
    except ValueError:
        return None
    if words[: len(context["command"])] != context["command"]:
        return None
    args = words[len(context["command"]) :]
    if len(args) % 2 or any(args[index] not in {"--path", "--glob"} for index in range(0, len(args), 2)):
        return None
    paths = tuple(args[index + 1] for index in range(0, len(args), 2) if args[index] == "--path")
    globs = tuple(args[index + 1] for index in range(0, len(args), 2) if args[index] == "--glob")
    try:
        SourceDiscovery(paths or (".",), globs, ()).verify()
    except ValueError:
        # Failed selector attempts remain in the ledger without being bound.
        # Capture and integrity failures below must still reject compilation.
        return None
    capture_path = context["capture_path"]
    if not isinstance(capture_path, str):
        msg = "source discovery capture_path must be a string"
        raise TypeError(msg)
    query, digest = load_discovery(Path(capture_path), tuple(dispatch["source_state"]), paths, globs)
    return query, (capture_path, digest)


def main() -> int:
    """Print a bounded captured-path selection without running external commands."""
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--source-state", required=True)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--glob", action="append", default=[])
    args = parser.parse_args()
    try:
        verify_current_snapshot()
        query, digest = load_discovery(args.capture, tuple(args.source_state.split(",")), tuple(args.path), tuple(args.glob))
        print(json.dumps({**asdict(query), "capture_digest": digest}, sort_keys=True))
    except (OSError, ValueError, TypeError) as error:
        print(f"review_graph_discovery: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
