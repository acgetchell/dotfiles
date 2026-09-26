"""Exercise instruction invalidation independently of review conclusions."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from instruction_receipt import load_instructions


def test_unchanged_pass_reuses_bodies_and_shared_references(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text("domain checklist\n")
    (tmp_path / "common.md").write_text("shared contract\n")
    paths = ["body.md", "common.md"]
    text, ledger, first = load_instructions(tmp_path, paths, {}, context="live", scope="source1", skill_id="api")
    assert "domain checklist" in text
    assert "shared contract" in text
    assert {row["status"] for row in first["files"]} == {"loaded"}
    text, ledger, reused = load_instructions(tmp_path, paths, ledger, context="live", scope="source1", skill_id="api")
    assert text == ""
    assert {row["status"] for row in reused["files"]} == {"reused"}
    text, _, _ = load_instructions(tmp_path, ["common.md"], ledger, context="live", scope="source1", skill_id="tests")
    assert text == ""


@pytest.mark.parametrize("change", ["body", "reference", "selection", "scope", "context"])
def test_required_changes_force_complete_pass_reload(tmp_path: Path, change: str) -> None:
    paths = ["body.md", "reference.md"]
    for name in paths:
        (tmp_path / name).write_text(name)
    _, ledger, _ = load_instructions(tmp_path, paths, {}, context="live", scope="source1", skill_id="api")
    context, scope = "live", "source1"
    if change in {"body", "reference"}:
        (tmp_path / f"{change}.md").write_text("changed contract")
    elif change == "selection":
        (tmp_path / "extra.md").write_text("new required reference")
        paths.append("extra.md")
    elif change == "scope":
        scope = "source2"
    else:
        context = "after-compaction"
    text, _, receipt = load_instructions(tmp_path, paths, ledger, context=context, scope=scope, skill_id="api")
    assert text
    assert {row["status"] for row in receipt["files"]} == {"loaded"}


def test_missing_or_outside_reference_fails_before_recording(tmp_path: Path) -> None:
    ledger: dict[str, Any] = {}
    with pytest.raises(FileNotFoundError):
        load_instructions(tmp_path, ["missing.md"], ledger, context="live", scope="source1", skill_id="api")
    (tmp_path / "nested").mkdir()
    (tmp_path / "outside.md").write_text("outside")
    with pytest.raises(ValueError, match="inside"):
        load_instructions(tmp_path / "nested", ["../outside.md"], ledger, context="live", scope="source1", skill_id="api")
    assert ledger == {}
