"""Deliver and acknowledge bounded instruction chunks in a live review context."""

import argparse
import json
import secrets
import sys
import tempfile
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

VERSION = 2
MAX_CHUNK_BYTES = 8192


class InstructionFile(TypedDict):
    """Identify a required file and its delivery status in this pass."""

    path: str
    sha256: str
    bytes: int
    status: Literal["pending", "loaded", "reused"]
    reread: bool


class Receipt(TypedDict):
    """Record delivery for one ordered view under the ledger's scope and context."""

    skill_id: str
    signature: str
    invalidated: bool
    files: list[InstructionFile]


class PassState(TypedDict):
    """Track acknowledged progress and the current offer for an instruction view."""

    receipt: Receipt
    offset: int
    offered_end: int
    token: str | None


@dataclass(frozen=True)
class Delivery:
    """One UTF-8 chunk ending with a token the recipient can acknowledge."""

    path: str
    sha256: str
    start: int
    end: int
    total_bytes: int
    content: bytes
    token: str

    def render(self) -> bytes:
        """Frame exact instruction bytes with byte offsets and an end marker."""
        header = {"path": self.path, "sha256": self.sha256, "start": self.start, "end": self.end, "bytes": self.total_bytes}
        return json.dumps(header).encode("ascii") + b"\n" + self.content + f"\n<!-- ACK {self.token} -->\n".encode("ascii")


def digest(content: bytes) -> str:
    """Return a content identity."""
    return sha256(content).hexdigest()


def read_view(root: Path, paths: list[str]) -> dict[str, bytes]:
    """Read the ordered, unique canonical files under the skills root."""
    if not paths:
        raise ValueError("At least one instruction path is required")  # noqa: EM101
    contents: dict[str, bytes] = {}
    for name in paths:
        path = (root / name).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("Instruction paths must remain inside the skills root")  # noqa: EM101
        canonical = path.relative_to(root).as_posix()
        if canonical in contents:
            raise ValueError("Instruction paths resolve to the same file")  # noqa: EM101
        content = path.read_bytes()
        content.decode("utf-8")  # Fail before offering part of an invalid view.
        contents[canonical] = content
    return contents


def start_pass(skill_id: str, signature: str, files: list[InstructionFile], loaded: dict[str, str], *, invalidated: bool) -> PassState:
    """Reuse previously acknowledged files unless the required view changed."""
    for file in files:
        cached = loaded.get(file["path"]) == file["sha256"]
        file["reread"] = cached and invalidated
        if cached and not invalidated:
            file["status"] = "reused"
    return {"receipt": {"skill_id": skill_id, "signature": signature, "invalidated": invalidated, "files": files}, "offset": 0, "offered_end": 0, "token": None}


def acknowledge(state: PassState, token: str, signature: str, loaded: dict[str, str]) -> None:
    """Accept the current offer and admit a file only after its last chunk."""
    if state["receipt"]["signature"] != signature or state["token"] != token:
        raise ValueError("Acknowledgement does not match the current instruction delivery")  # noqa: EM101
    file = next(file for file in state["receipt"]["files"] if file["status"] == "pending")
    state["offset"] = state["offered_end"]
    state["token"] = None
    if state["offset"] == file["bytes"]:
        loaded[file["path"]] = file["sha256"]
        file["status"] = "loaded"
        state["offset"] = 0


def offer_chunk(state: PassState, contents: dict[str, bytes], chunk_bytes: int) -> Delivery | None:
    """Offer the next contiguous chunk, reusing its token on an unchanged retry."""
    file = next((file for file in state["receipt"]["files"] if file["status"] == "pending"), None)
    if file is None:
        return None
    content = contents[file["path"]]
    start = state["offset"]
    end = min(start + chunk_bytes, len(content))
    # A UTF-8 continuation byte belongs in the next chunk with its leading byte.
    while end < len(content) and content[end] & 0xC0 == 0x80:
        end -= 1
    token = state["token"]
    if token is None or state["offered_end"] != end:
        token = secrets.token_hex(16)
        state["token"] = token
        state["offered_end"] = end
    return Delivery(file["path"], file["sha256"], start, end, file["bytes"], content[start:end], token)


def deliver_instructions(  # noqa: PLR0913 - explicit receipt identities and delivery inputs
    root: Path, paths: list[str], ledger: dict[str, Any], *, context: str, scope: str, skill_id: str, ack: str | None = None, chunk_bytes: int = MAX_CHUNK_BYTES
) -> tuple[Delivery | None, dict[str, Any], Receipt]:
    """Optionally acknowledge the previous chunk and offer the next one.

    Scope identifies the authorized review boundary. Source fingerprints
    belong to findings and validation evidence, outside this ledger.
    """
    if not context or not scope or not skill_id:
        raise ValueError("Context, scope, and pass ID are required")  # noqa: EM101
    if not 4 <= chunk_bytes <= MAX_CHUNK_BYTES:
        raise ValueError(f"Chunk size must be between 4 and {MAX_CHUNK_BYTES} bytes")
    root = root.resolve()
    contents = read_view(root, paths)
    identity = {"version": VERSION, "root": str(root), "context": context, "scope": scope}
    ledger = {**identity, "passes": {}, "loaded": {}} if any(ledger.get(key) != value for key, value in identity.items()) else deepcopy(ledger)
    files: list[InstructionFile] = [
        {"path": name, "sha256": digest(content), "bytes": len(content), "status": "pending", "reread": False} for name, content in contents.items()
    ]
    signature = digest(json.dumps([(file["path"], file["sha256"]) for file in files]).encode("ascii"))
    passes = cast("dict[str, PassState]", ledger["passes"])
    loaded = cast("dict[str, str]", ledger["loaded"])
    state = passes.get(skill_id)
    if ack is not None:
        if state is None:
            raise ValueError("No instruction delivery to acknowledge in this scope and context")  # noqa: EM101
        acknowledge(state, ack, signature, loaded)
    else:
        changed = state is not None and state["receipt"]["signature"] != signature
        if state is None or changed or state["token"] is None:
            state = start_pass(skill_id, signature, files, loaded, invalidated=changed)
            passes[skill_id] = state
    return offer_chunk(state, contents, chunk_bytes), ledger, state["receipt"]


def save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    """Replace the ledger atomically after the next state has been serialized."""
    with ExitStack() as cleanup:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            cleanup.callback(temporary.unlink, missing_ok=True)
            output.write(json.dumps(ledger, indent=2) + "\n")
        temporary.replace(path)


def main() -> None:
    """Print one offer or a compact completion receipt for a serial caller."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--scope", required=True, help="Stable authorized review scope ID, independent of source contents")
    parser.add_argument("--skill-id", required=True)
    parser.add_argument("--ack", help="Token at the end of the previous fully received chunk")
    parser.add_argument("--chunk-bytes", type=int, default=MAX_CHUNK_BYTES)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    try:
        ledger = json.loads(args.ledger.read_text(encoding="utf-8")) if args.ledger.exists() else {}
        delivery, ledger, receipt = deliver_instructions(
            args.root, args.paths, ledger, context=args.context, scope=args.scope, skill_id=args.skill_id, ack=args.ack, chunk_bytes=args.chunk_bytes
        )
    except ValueError as error:
        parser.error(str(error))

    save_ledger(args.ledger, ledger)
    if delivery is None:
        print(json.dumps({"skill_id": receipt["skill_id"], "signature": receipt["signature"], "complete": True}))
    else:
        sys.stdout.buffer.write(delivery.render())


if __name__ == "__main__":
    main()
