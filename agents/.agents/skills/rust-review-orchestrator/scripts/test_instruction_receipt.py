"""Exercise delivery and invalidation independently of review conclusions."""

import json
import re
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from instruction_receipt import deliver_instructions, digest

if TYPE_CHECKING:
    from instruction_receipt import Receipt

SCOPE = "repository:changed-files"


def receive(  # noqa: PLR0913 - vary each receipt identity in the fixture
    root: Path, paths: list[str], ledger: dict[str, Any], *, context: str = "live", scope: str = SCOPE, skill_id: str = "api"
) -> tuple[bytes, dict[str, Any], Receipt]:
    step = partial(deliver_instructions, root, paths, context=context, scope=scope, skill_id=skill_id)
    delivery, ledger, receipt = step(ledger)
    contents = bytearray()
    while delivery is not None:
        contents.extend(delivery.content)
        delivery, ledger, receipt = step(ledger, ack=delivery.token)
    return bytes(contents), ledger, receipt


def test_unchanged_pass_reuses_bodies_and_shared_references(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_bytes(b"domain checklist\n")
    (tmp_path / "common.md").write_bytes(b"shared contract\n")
    paths = ["body.md", "common.md"]
    body, ledger, first = receive(tmp_path, paths, {})
    assert body == b"domain checklist\nshared contract\n"
    assert [row["status"] for row in first["files"]] == ["loaded", "loaded"]
    body, ledger, reused = receive(tmp_path, paths, ledger)
    assert body == b""
    assert reused["signature"] == first["signature"]
    assert [row["status"] for row in reused["files"]] == ["reused", "reused"]
    body, _, shared = receive(tmp_path, ["common.md"], ledger, skill_id="tests")
    assert body == b""
    assert [row["status"] for row in shared["files"]] == ["reused"]


@pytest.mark.parametrize("change", ["body", "reference", "selection", "order", "scope", "context"])
def test_required_changes_force_complete_pass_reload(tmp_path: Path, change: str) -> None:
    paths = ["body.md", "reference.md"]
    for name in paths:
        (tmp_path / name).write_bytes(name.encode())
    _, ledger, original = receive(tmp_path, paths, {})
    context, scope = "live", SCOPE
    if change in {"body", "reference"}:
        (tmp_path / f"{change}.md").write_bytes(b"changed contract")
    elif change == "selection":
        (tmp_path / "extra.md").write_bytes(b"new required reference")
        paths.append("extra.md")
    elif change == "order":
        paths.reverse()
    elif change == "scope":
        scope = "repository:all-files"
    else:
        context = "after-compaction"
    body, _, receipt = receive(tmp_path, paths, ledger, context=context, scope=scope)
    assert body == b"".join((tmp_path / name).read_bytes() for name in paths)
    assert [row["status"] for row in receipt["files"]] == ["loaded"] * len(paths)
    assert receipt["invalidated"] == (change not in {"scope", "context"})
    assert (receipt["signature"] == original["signature"]) == (change in {"scope", "context"})


def test_changed_reference_rejects_an_unacknowledged_offer(tmp_path: Path) -> None:
    paths = ["body.md", "reference.md"]
    (tmp_path / "body.md").write_bytes(b"domain checklist\n")
    reference = tmp_path / "reference.md"
    reference.write_bytes(b"old reference\n")
    step = partial(deliver_instructions, tmp_path, paths, context="live", scope=SCOPE, skill_id="api")
    body, ledger, _ = step({})
    assert body is not None
    pending, ledger, _ = step(ledger, ack=body.token)
    assert pending is not None
    reference.write_bytes(b"new reference\n")
    with pytest.raises(ValueError, match="does not match"):
        step(ledger, ack=pending.token)
    content, _, receipt = receive(tmp_path, paths, ledger)
    assert content == b"domain checklist\nnew reference\n"
    assert receipt["invalidated"] is True
    assert [row["reread"] for row in receipt["files"]] == [True, False]


def test_missing_or_outside_reference_fails_before_recording(tmp_path: Path) -> None:
    ledger: dict[str, Any] = {}
    step = partial(deliver_instructions, context="live", scope=SCOPE, skill_id="api")
    with pytest.raises(FileNotFoundError):
        step(tmp_path, ["missing.md"], ledger)
    (tmp_path / "nested").mkdir()
    (tmp_path / "outside.md").write_bytes(b"outside")
    with pytest.raises(ValueError, match="inside"):
        step(tmp_path / "nested", ["../outside.md"], ledger)
    assert ledger == {}


def test_old_ledger_cannot_supply_an_acknowledged_receipt(tmp_path: Path) -> None:
    payload = b"unacknowledged checklist\n"
    (tmp_path / "body.md").write_bytes(payload)
    ledger = {"version": 1, "root": str(tmp_path.resolve()), "context": "live", "scope": SCOPE, "passes": {}, "loaded": {"body.md": digest(payload)}}
    delivery, ledger, receipt = deliver_instructions(tmp_path, ["body.md"], ledger, context="live", scope=SCOPE, skill_id="api")
    assert delivery is not None
    assert delivery.content == payload
    assert ledger["loaded"] == {}
    assert receipt["files"][0]["status"] == "pending"


@pytest.mark.parametrize("damage", ["unknown-status", "missing-file", "completed-with-offer", "out-of-range", "split-start", "split-end", "invalid-token"])
def test_invalid_saved_progress_is_rejected_on_retry_and_ack(tmp_path: Path, damage: str) -> None:
    (tmp_path / "body.md").write_bytes("one🦀two".encode())
    step = partial(deliver_instructions, tmp_path, ["body.md"], context="live", scope=SCOPE, skill_id="api", chunk_bytes=4)
    offered, ledger, _ = step({})
    assert offered is not None
    state = ledger["passes"]["api"]
    match damage:
        case "unknown-status":
            state["receipt"]["files"][0]["status"] = "complete"
        case "missing-file":
            state["receipt"]["files"].clear()
        case "completed-with-offer":
            state["receipt"]["files"][0]["status"] = "loaded"
        case "out-of-range":
            state["offered_end"] = 100
        case "split-start":
            state.update(offset=4, offered_end=7)
        case "split-end":
            state["offered_end"] = 4
        case "invalid-token":
            state["token"] = "é" + offered.token[1:]
    for ack in (None, offered.token):
        with pytest.raises(ValueError, match="Invalid instruction ledger"):
            step(ledger, ack=ack)


def test_smaller_retry_replaces_only_the_unacknowledged_offer(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_bytes(b"firstsecondthird")
    step = partial(deliver_instructions, tmp_path, ["body.md"], context="live", scope=SCOPE, skill_id="api")
    first, ledger, _ = step({}, chunk_bytes=5)
    assert first is not None
    large, ledger, _ = step(ledger, ack=first.token)
    assert large is not None
    retry, ledger, _ = step(ledger, chunk_bytes=6)
    assert retry is not None
    assert retry.start == large.start == 5
    assert retry.content == b"second"
    with pytest.raises(ValueError, match="does not match"):
        step(ledger, ack=large.token)
    last, ledger, _ = step(ledger, ack=retry.token)
    assert last is not None
    assert last.content == b"third"
    end, _, receipt = step(ledger, ack=last.token)
    assert end is None
    assert receipt["files"][0]["status"] == "loaded"


def test_truncated_cli_response_requires_acknowledgement_and_resumes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONIOENCODING", "ascii")
    payload = b"a\r\n" + "🦀".encode() + b"\r\n"
    (tmp_path / "body.md").write_bytes(payload)
    (tmp_path / "empty.md").write_bytes(b"")
    ledger = tmp_path / "ledger.json"
    helper = Path(__file__).with_name("instruction_receipt.py")
    command = [
        sys.executable,
        str(helper),
        "--root",
        str(tmp_path),
        "--ledger",
        str(ledger),
        "--context",
        "live",
        "--scope",
        SCOPE,
        "--skill-id",
        "api",
        "--chunk-bytes",
        "5",
        "body.md",
        "empty.md",
    ]

    def invoke(*args: str) -> bytes:
        return subprocess.run([*command, *args], capture_output=True, check=True, timeout=10).stdout  # noqa: S603

    def ack_token(response: bytes) -> str:
        footer = response.rsplit(b"\n", 2)[-2]
        match = re.fullmatch(rb"<!-- ACK ([0-9a-f]{32}) -->", footer)
        assert match is not None
        token = match.group(1)
        assert isinstance(token, bytes)
        return token.decode("ascii")

    first = invoke()
    assert first.split(b"\n", 1)[1].startswith(b"a\r\n\n<!-- ACK ")
    second = invoke("--ack", ack_token(first))
    header, _, _ = second.partition(b"\n")
    assert (json.loads(header)["start"], json.loads(header)["end"]) == (3, 8)
    truncated = second[: len(header) + 3]
    assert b"<!-- ACK " not in truncated
    assert json.loads(ledger.read_bytes())["loaded"] == {}
    assert invoke() == second

    rejected = subprocess.run([*command, "--ack", ack_token(first)], capture_output=True, check=False, timeout=10)  # noqa: S603
    assert rejected.returncode == 2
    assert b"does not match" in rejected.stderr
    assert invoke() == second
    third = invoke("--ack", ack_token(second))
    empty = invoke("--ack", ack_token(third))
    assert list(json.loads(ledger.read_bytes())["loaded"]) == ["body.md"]
    assert json.loads(empty.split(b"\n", 1)[0])["path"] == "empty.md"
    actual = b"".join(response.split(b"\n", 1)[1].rsplit(b"\n", 2)[0] for response in (first, second, third))
    assert actual == payload
    completed = json.loads(invoke("--ack", ack_token(empty)))
    assert completed["complete"] is True
    stored = json.loads(ledger.read_bytes())["passes"]["api"]["receipt"]
    assert stored["signature"] == completed["signature"]
    assert [file["status"] for file in stored["files"]] == ["loaded", "loaded"]
