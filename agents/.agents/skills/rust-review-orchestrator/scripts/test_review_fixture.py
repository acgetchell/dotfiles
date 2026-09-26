"""The controlled review case distinguishes discarded hooks from its correction."""

import shutil
from typing import TYPE_CHECKING

from review_fixture import SCRIPT, validate_source

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
