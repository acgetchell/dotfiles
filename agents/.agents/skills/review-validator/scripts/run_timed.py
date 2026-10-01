"""Run an exact argument vector with portable, execution-side timing evidence."""

import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO


@dataclass(frozen=True)
class Launch:
    """A coordinator-supplied command; no shell parsing or environment rewriting."""

    argv: tuple[str, ...]
    working_directory: str


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for name, value in pairs:
        if name in fields:
            msg = "duplicate launch field"
            raise ValueError(msg)
        fields[name] = value
    return fields


def read_launch(path: Path) -> Launch:
    """Reject ambiguous inputs and unsupported wrapper options before execution."""
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields)
    if not isinstance(value, dict) or set(value) != {"schema_version", "argv", "working_directory"}:
        msg = "expected schema_version, argv, and working_directory only"
        raise ValueError(msg)
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        msg = "unsupported launch schema"
        raise ValueError(msg)
    argv = value["argv"]
    if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) or "\0" in arg for arg in argv) or not argv[0]:
        msg = "argv must be a nonempty string array with an executable"
        raise ValueError(msg)
    directory = value["working_directory"]
    if not isinstance(directory, str) or "\0" in directory or not Path(directory).is_absolute() or not Path(directory).is_dir():
        msg = "working_directory must name an existing absolute directory"
        raise ValueError(msg)
    return Launch(tuple(argv), directory)


def _record(stream: TextIO, event: dict[str, object]) -> None:
    stream.write(json.dumps(event, ensure_ascii=True, allow_nan=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _stop(process: subprocess.Popen[bytes]) -> int:
    if process.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
    try:
        return process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait()


def execute(launch: Launch, stream: TextIO) -> int:
    """Time process creation through wait, retaining command and wrapper failures."""
    _record(
        stream, {"schema_version": 1, "event": "attempt-started", "argv": launch.argv, "working_directory": launch.working_directory, "platform": sys.platform}
    )
    started = time.monotonic_ns()
    try:
        # Inherit all three streams and the environment; never use shell=True.
        process = subprocess.Popen(launch.argv, cwd=launch.working_directory)  # noqa: S603 -- exact authorized dispatch arguments
    except OSError as error:
        _record(
            stream,
            {
                "event": "finished",
                "status": "launch-failed",
                "command_started": False,
                "exit_code": None,
                "elapsed_seconds": (time.monotonic_ns() - started) / 1_000_000_000,
                "error_type": type(error).__name__,
                "errno": error.errno,
            },
        )
        return 2

    status = "completed"
    try:
        code = process.wait()
    except KeyboardInterrupt:
        code = _stop(process)
        status = "interrupted"
    _record(
        stream,
        {"event": "finished", "status": status, "command_started": True, "exit_code": code, "elapsed_seconds": (time.monotonic_ns() - started) / 1_000_000_000},
    )
    if status == "interrupted":
        return 130
    # Keep the actual negative subprocess return code in evidence on POSIX.
    return 128 - code if os.name == "posix" and code < 0 else code


def main(argv: list[str] | None = None) -> int:
    """Run one command and write a new, private, append-only JSONL receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="coordinator-approved launch JSON")
    parser.add_argument("--receipt", type=Path, required=True, help="new absolute path approved for timing evidence")
    args = parser.parse_args(argv)
    try:
        launch = read_launch(args.input)
        if not args.receipt.is_absolute():
            msg = "receipt path must be absolute"
            raise ValueError(msg)
    except OSError, ValueError:
        print("run_timed: invalid or unreadable launch specification; command not started", file=sys.stderr)
        return 2
    try:
        fd = os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            return execute(launch, stream)
    except OSError:
        print("run_timed: timing receipt unavailable; inspect existing evidence before retrying", file=sys.stderr)
        return 74


if __name__ == "__main__":
    raise SystemExit(main())
