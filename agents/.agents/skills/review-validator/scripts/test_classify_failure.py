"""Retained sandbox panic classification never replaces original failure evidence."""

import hashlib
import json
lazy from pathlib import Path

import pytest
from classify_failure import classify_failure, main

PANIC = (
    b"thread 'main' panicked at /build/registry/system-configuration-0.5.1/src/dynamic_store.rs:154:9:\n"
    b"Attempted to create a NULL object.\n"
    b"error: Recipe `toml-fix` failed with exit code 101\n"
)


@pytest.mark.parametrize("exit_code", [1, 101])
def test_taplo_panic_is_infrastructure_with_original_status(exit_code: int) -> None:
    result = classify_failure(PANIC, tool="taplo", platform="darwin", sandbox="workspace-write", exit_code=exit_code)
    assert result["failure_kind"] == "infrastructure"
    assert result["diagnosis"] == "macos-taplo-system-configuration-sandbox"
    assert result["exit_code"] == exit_code
    assert result["log_digest"] == "sha256:" + hashlib.sha256(PANIC).hexdigest()


@pytest.mark.parametrize(
    ("log", "tool", "platform", "sandbox", "exit_code"),
    [
        (b"error: invalid TOML at line 3", "taplo", "darwin", "workspace-write", 1),
        (b"Attempted to create a NULL object.", "taplo", "darwin", "workspace-write", 101),
        (PANIC.replace(b"system-configuration", b"another-crate"), "taplo", "darwin", "workspace-write", 101),
        (PANIC, "taplo", "linux", "workspace-write", 101),
        (PANIC, "another-tool", "darwin", "workspace-write", 101),
        (PANIC, "taplo", "darwin", "require_escalated", 101),
        (PANIC, "taplo", "darwin", "workspace-write", 0),
        (b"", "taplo", "darwin", "workspace-write", 1),
    ],
)
def test_other_failures_do_not_receive_sandbox_retry(log: bytes, tool: str, platform: str, sandbox: str, exit_code: int) -> None:
    result = classify_failure(log, tool=tool, platform=platform, sandbox=sandbox, exit_code=exit_code)
    assert result["diagnosis"] == "unclassified"
    assert result["failure_kind"] == "inconclusive"


def test_cli_reads_existing_log_without_modifying_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "original.log"
    log.write_bytes(PANIC)
    assert main(["--log", str(log), "--tool", "taplo", "--platform", "darwin", "--sandbox", "workspace-write", "--exit-code", "1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["failure_kind"] == "infrastructure"
    assert result["log_path"] == str(log)
    assert log.read_bytes() == PANIC
    assert list(tmp_path.iterdir()) == [log]
