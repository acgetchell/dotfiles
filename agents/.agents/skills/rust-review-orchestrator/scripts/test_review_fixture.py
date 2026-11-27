"""The controlled review case distinguishes discarded hooks from its correction."""

import shutil
from typing import TYPE_CHECKING

import pytest
from instruction_receipt import MAX_CHUNK_BYTES
from review_fixture import OVERSIZED_VIEW, SCRIPT, SKILLS, library_artifact, measure_resumable_delivery, prepare_repaired_source, run, validate_source

if TYPE_CHECKING:
    from pathlib import Path


def test_callback_probe_distinguishes_original_and_corrected_warmup(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.mkdir()
    before = validate_source(original)
    warmup = [line for line in before["callbacks"] if "warmup=true" in line]
    controls = [line for line in before["callbacks"] if "warmup=false" in line]
    assert len(warmup) == 4
    assert all(line.endswith("callbacks=100") for line in warmup)
    assert len(controls) == 4
    assert all(line.endswith("callbacks=0") for line in controls)

    source = tmp_path / "source"
    prepare_repaired_source(source)
    corrected = tmp_path / "corrected"
    corrected.mkdir()
    after = validate_source(corrected, source)
    assert after["source_sha256"] != before["source_sha256"]
    assert len(after["callbacks"]) == 8
    assert all(line.endswith("callbacks=0") for line in after["callbacks"])


def test_oversized_view_resumes_and_survives_source_only_repair(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.mkdir()
    before = validate_source(original)
    report, after = measure_resumable_delivery(SKILLS, tmp_path, original_source=before["source_sha256"])

    receipts = report["receipts"]
    first = receipts["first_load"]
    assert [file["path"] for file in first["files"]] == OVERSIZED_VIEW
    assert [file["status"] for file in receipts["interrupted"]["receipt"]["files"]] == ["loaded", *(["pending"] * (len(OVERSIZED_VIEW) - 1))]
    assert [file["status"] for file in first["files"]] == ["loaded"] * len(OVERSIZED_VIEW)
    assert len(first["chunk_sizes"]) >= len(OVERSIZED_VIEW)
    assert max(first["chunk_sizes"]) <= MAX_CHUNK_BYTES
    expected_files = [f"<!-- {file['path']} sha256={file['sha256']} -->\n".encode() + (SKILLS / file["path"]).read_bytes() for file in first["files"]]
    assert (tmp_path / "oversized-view.txt").read_bytes() == b"\n".join(expected_files)
    assert report["first_load_bytes"] == sum(file["bytes"] for file in first["files"]) > MAX_CHUNK_BYTES
    assert report["repeat_bytes"] == report["after_repair_bytes"] == 0
    for name in ("repeat", "after_repair"):
        assert receipts[name]["signature"] == first["signature"]
        assert [file["status"] for file in receipts[name]["files"]] == ["reused"] * len(OVERSIZED_VIEW)
    assert report["source_evidence"] == {
        "original_source_sha256": before["source_sha256"],
        "repaired_source_sha256": after["source_sha256"],
        "original_source_evidence_eligible": False,
    }
    assert before["files"].keys() == after["files"].keys()
    assert [path for path in before["files"] if before["files"][path] != after["files"][path]] == ["src/adaptive.rs"]


@pytest.mark.parametrize("configuration", ["environment", "config"])
def test_callback_probe_with_explicit_cargo_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configuration: str) -> None:
    source = tmp_path / "source"
    shutil.copytree(SCRIPT / "fixtures/warmup", source)
    host = next(line.removeprefix("host: ") for line in run(["rustc", "-vV"], source).splitlines() if line.startswith("host: "))
    monkeypatch.delenv("CARGO_BUILD_TARGET", raising=False)
    if configuration == "environment":
        monkeypatch.setenv("CARGO_BUILD_TARGET", host)
    else:
        (source / ".cargo").mkdir()
        (source / ".cargo/config.toml").write_text(f'[build]\ntarget = "{host}"\n')
    output = tmp_path / "output"
    output.mkdir()

    report = validate_source(output, source)

    # Cargo 1.100 uses debug/build/.../out instead of debug/deps for intermediates.
    library = library_artifact((output / "validation.txt").read_text())
    assert library.is_file()
    assert library.is_relative_to(output / "target" / host / "debug")
    assert len(report["callbacks"]) == 8
    assert all(line.endswith("callbacks=100" if "warmup=true" in line else "callbacks=0") for line in report["callbacks"])


@pytest.mark.parametrize(
    ("cargo_output", "message"),
    [
        ("", "Expected one warmup_fixture rlib"),
        ("{malformed", "Expecting property name"),
        ('{"reason":"compiler-artifact","target":{"name":"warmup_fixture"},"filenames":["one.rlib","two.rlib"]}', "Expected one warmup_fixture rlib"),
    ],
)
def test_library_artifact_rejects_missing_malformed_or_ambiguous_output(cargo_output: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        library_artifact(cargo_output)
