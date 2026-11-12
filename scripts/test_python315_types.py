"""Prove Python 3.15 metadata typing catches shape errors at consumer boundaries."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
GRAPH = REPOSITORY / "agents/.agents/skills/review-graph/scripts"


@pytest.mark.parametrize(
    ("statement", "valid", "field"),
    [
        ('source: SourceIdentity = {"commit": "abc", "content_digest": "sha256:abc"}', True, ""),
        ('source: SourceIdentity = {"commit": "abc", "content_digest": "sha256:abc", "credential": "secret"}', False, "credential"),
        (
            (
                'tools: ToolIdentities = {"new-tool": {"executable": None, "identity": "missing", '
                '"expected_version": None, "available": False, "pin_matches": False}}'
            ),
            True,
            "",
        ),
        ('tools: ToolIdentities = {"new-tool": "wrong"}', False, "ToolIdentity"),
        ('error: SchemaErrorPayload = {"schema_id": "schema", "diagnostics": []}', True, ""),
        ('error: SchemaErrorPayload = {"schema_id": "schema", "diagnostics": [], "extra": True}', False, "extra"),
        ("def transition(source: ExternalSourceTransition) -> MetadataTransition:\n    return source", True, ""),
        (
            (
                "def metadata_only(value: ExternalMetadataTransition) -> None:\n    pass\n"
                "def consume(source: ExternalSourceTransition) -> None:\n    metadata_only(source)"
            ),
            False,
            "ExternalSourceTransition",
        ),
        ("def repair_paths(value: MetadataTransition) -> tuple[str, ...]:\n    return value.repair_paths", False, "repair_paths"),
        (
            "def source(before: ReviewSourceSnapshot, after: ReviewSourceSnapshot) -> MetadataTransition:\n    return ExternalSourceTransition(before, after)",
            False,
            "external_source_actor",
        ),
    ],
)
def test_metadata_consumers_accept_only_the_declared_shape(tmp_path: Path, statement: str, *, valid: bool, field: str) -> None:
    """Invalid snippets stay outside the source inventory and are checked by real ty."""
    probe = tmp_path / "consumer.py"
    probe.write_text(
        "from linux_review import SourceIdentity, ToolIdentities\nfrom review_graph_schema import SchemaErrorPayload\n"
        "from review_graph_reuse import ExternalMetadataTransition, ExternalSourceTransition, MetadataTransition, ReviewSourceSnapshot\n" + statement + "\n"
    )
    executable = shutil.which("ty")
    assert executable is not None
    result = subprocess.run(  # noqa: S603 - pinned type checker and disposable first-party consumer.
        [
            executable,
            "check",
            "--project",
            str(REPOSITORY),
            "--extra-search-path",
            str(REPOSITORY / "scripts"),
            "--extra-search-path",
            str(GRAPH),
            "--output-format",
            "concise",
            "--error",
            "all",
            str(probe),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if valid:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode == 1, result.stdout + result.stderr
        assert field in result.stdout + result.stderr
    assert probe.read_text().endswith(statement + "\n")
