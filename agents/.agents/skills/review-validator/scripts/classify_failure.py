"""Classify retained diagnostics without executing commands or changing evidence."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def classify_failure(log: bytes, *, tool: str, platform: str, sandbox: str, exit_code: int) -> dict[str, Any]:
    """Recognize the observed Taplo/macOS sandbox signature, not generic TOML errors."""
    text = log.decode("utf-8", errors="replace")
    known = (
        exit_code != 0
        and tool == "taplo"
        and platform == "darwin"
        and sandbox == "workspace-write"
        and re.search(r"panicked at [^\n]*system-configuration-[0-9.]+/src/dynamic_store\.rs:\d+(?::\d+)?:?\s*\n?Attempted to create a NULL object\.", text)
        is not None
    )
    return {
        "schema_version": 1,
        "diagnosis": "macos-taplo-system-configuration-sandbox" if known else "unclassified",
        "failure_kind": "infrastructure" if known else "inconclusive",
        "tool": tool,
        "platform": platform,
        "sandbox": sandbox,
        "exit_code": exit_code,
        "log_digest": "sha256:" + hashlib.sha256(log).hexdigest(),
        "log_byte_count": len(log),
        "retry": (
            "Preserve this failure and request one approved retry of the identical canonical command, working directory, inputs, and toolchain with "
            "sandbox escalation. Record the permission change and separate output; stop if denied or the retry fails."
            if known
            else "Inspect the retained diagnostics; no retry is prescribed."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Print a diagnostic receipt for an existing log; never launch a retry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--tool", required=True, help="actual failing tool, including when called through a recipe")
    parser.add_argument("--platform", required=True, help="actual executor platform, e.g. darwin")
    parser.add_argument("--sandbox", required=True, help="observed permission boundary, e.g. workspace-write")
    parser.add_argument("--exit-code", type=int, required=True, help="observed command exit code, including wrapper status")
    args = parser.parse_args(argv)
    try:
        content = args.log.read_bytes()
    except OSError as error:
        parser.error(str(error))
    result = classify_failure(content, tool=args.tool, platform=args.platform, sandbox=args.sandbox, exit_code=args.exit_code)
    print(json.dumps({**result, "log_path": str(args.log.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
