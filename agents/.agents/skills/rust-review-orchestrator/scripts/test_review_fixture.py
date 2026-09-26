"""The controlled review case distinguishes discarded hooks from its correction."""

import shutil
from typing import TYPE_CHECKING

import pytest
from review_fixture import SCRIPT, library_artifact, run, validate_source

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
    shutil.copytree(SCRIPT / "fixtures/warmup", source)
    adaptive = source / "src/adaptive.rs"
    adaptive.write_text(
        adaptive.read_text()
        .replace("self.step_mut().outcome", "self.proposal.transition(&mut self.state)")
        .replace("self.step_delayed().outcome", "self.proposal.transition(&mut self.state)")
    )
    corrected = tmp_path / "corrected"
    corrected.mkdir()
    after = validate_source(corrected, source)
    assert after["source_sha256"] != before["source_sha256"]
    assert len(after["callbacks"]) == 8
    assert all(line.endswith("callbacks=0") for line in after["callbacks"])


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

    assert (output / "target" / host / "debug/deps").is_dir()
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
