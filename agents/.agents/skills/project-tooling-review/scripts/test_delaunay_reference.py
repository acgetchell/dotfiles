"""Keep documented external paths and commands within a reviewed tooling snapshot."""

import json
import re
from pathlib import Path


def test_delaunay_examples_match_maintained_snapshot() -> None:
    references = Path(__file__).resolve().parents[1] / "references"
    snapshot = json.loads((references / "delaunay-tooling-snapshot.json").read_bytes())
    examples = re.findall(r"`([^`]+)`", (references / "delaunay.md").read_text())
    commands = {example.removeprefix("just ") for example in examples if example.startswith("just ")}
    paths = {example for example in examples if ("/" in example and not example.startswith("//")) or example.endswith((".md", ".toml", ".yaml"))}
    assert commands <= set(snapshot["recipes"]), commands - set(snapshot["recipes"])
    supported_paths = set(snapshot["paths"]) | set(snapshot["generated_paths"])
    assert paths <= supported_paths, paths - supported_paths
    assert re.fullmatch(r"[0-9a-f]{40}", snapshot["revision"])
