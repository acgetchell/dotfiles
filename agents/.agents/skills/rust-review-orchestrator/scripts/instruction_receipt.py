"""Emit complete instruction files once per live review context, with provenance."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

VERSION = 1


def digest(content: bytes) -> str:
    """Return a content identity, not a token estimate."""
    return hashlib.sha256(content).hexdigest()


def load_instructions(  # noqa: PLR0913 - explicit receipt identities
    root: Path, paths: list[str], ledger: dict[str, Any], *, context: str, scope: str, skill_id: str
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Return emitted text, updated ledger, and this invocation's byte receipt."""
    if not context or not scope or not skill_id or not paths or len(set(paths)) != len(paths):
        message = "Context, scope, pass ID, and unique instruction paths are required"
        raise ValueError(message)
    root = root.resolve()
    contents: dict[str, bytes] = {}
    for name in paths:
        path = (root / name).resolve(strict=True)
        if not path.is_relative_to(root):
            message = "Instruction paths must remain inside the skills root"
            raise ValueError(message)
        canonical = path.relative_to(root).as_posix()
        if canonical in contents:
            message = "Instruction paths resolve to the same file"
            raise ValueError(message)
        contents[canonical] = path.read_bytes()
    identity = {"version": VERSION, "root": str(root), "context": context, "scope": scope}
    ledger = {**identity, "passes": {}, "loaded": {}} if any(ledger.get(key) != value for key, value in identity.items()) else json.loads(json.dumps(ledger))
    records = {name: {"sha256": digest(content), "bytes": len(content)} for name, content in contents.items()}
    signature = digest(json.dumps(records, sort_keys=True).encode())
    passes = cast("dict[str, str]", ledger["passes"])
    loaded = cast("dict[str, str]", ledger["loaded"])
    previous = passes.get(skill_id)
    invalidated = previous is not None and previous != signature
    emitted = []
    rows = []
    for name, content in contents.items():
        fingerprint = digest(content)
        cached = loaded.get(name) == fingerprint
        status = "reused" if cached and not invalidated else "loaded"
        rows.append({"path": name, **records[name], "status": status, "reread": status == "loaded" and cached})
        if status == "loaded":
            emitted.append(f"<!-- {name} sha256={fingerprint} -->\n{content.decode('utf-8')}")
            loaded[name] = fingerprint
    passes[skill_id] = signature
    receipt = {"skill_id": skill_id, "signature": signature, "invalidated": invalidated, "files": rows}
    return "\n".join(emitted), ledger, receipt


def main() -> None:
    """Load explicit paths; selection and semantic review remain the agent's job."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--scope", required=True, help="Stable scope receipt identity, including its source fingerprint")
    parser.add_argument("--skill-id", required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    ledger = json.loads(args.ledger.read_text()) if args.ledger.exists() else {}
    output, ledger, receipt = load_instructions(args.root, args.paths, ledger, context=args.context, scope=args.scope, skill_id=args.skill_id)
    print(output, end="")
    sys.stdout.flush()
    args.ledger.write_text(json.dumps(ledger, indent=2) + "\n")
    print(json.dumps(receipt), file=sys.stderr)


if __name__ == "__main__":
    main()
