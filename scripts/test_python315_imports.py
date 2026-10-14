"""Guard explicit lazy import boundaries and fixed review protocol labels."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
GRAPH_SCRIPTS = Path(__file__).resolve().parents[1] / "agents/.agents/skills/review-graph/scripts"


def test_label_import_defers_validation_without_changing_serialization() -> None:
    """Reading immutable labels need not load the Git validation dependency tree."""
    labels = {
        "fallback": "fallback absence and failure",
        "platform": "platform seams",
        "parser-errors": "parser suffixes and error branches",
        "unexpected-exceptions": "unexpected exception types",
        "test-boundaries": "changed tests and boundary cases",
    }
    program = (
        "import json, sys\n"
        "from review_graph_independent import CHECK_LABELS\n"
        "assert 'review_graph_git' not in sys.modules\n"
        "assert 'review_graph_schema' not in sys.modules\n"
        "try: CHECK_LABELS['fallback'] = 'changed'\n"
        "except TypeError: pass\n"
        "else: raise AssertionError('mutable protocol labels')\n"
        "print(json.dumps(CHECK_LABELS))\n"
    )
    result = subprocess.run(  # noqa: S603 - fresh local interpreter, fixed import probe.
        [sys.executable, "-c", program], cwd=GRAPH_SCRIPTS, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == json.dumps(labels) + "\n"


@pytest.mark.parametrize(
    ("module", "directory", "deferred"),
    [
        ("capture_scope", GRAPH_SCRIPTS, ("subprocess", "research_repo_tools.process", "review_graph_git_objects", "review_graph_reuse")),
        ("linux_review", REPOSITORY / "scripts", ("subprocess", "hashlib", "platform", "shutil", "tomllib")),
    ],
)
def test_metadata_import_defers_operational_dependencies(module: str, directory: Path, deferred: tuple[str, ...]) -> None:
    """Fresh processes prove import isolation without test-suite preloading."""
    program = f"import sys\nimport {module}\nassert not set({deferred!r}) & sys.modules.keys()\nprint('deferred')\n"
    result = subprocess.run(  # noqa: S603 - fixed local modules in fresh interpreter.
        [sys.executable, "-c", program], cwd=directory, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "deferred\n"


@pytest.mark.parametrize("path", [GRAPH_SCRIPTS / "capture_scope.py", REPOSITORY / "scripts/linux_review.py"])
def test_lazy_cli_help_resolves_dependencies_without_operational_effects(path: Path, tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local help command in empty working directory.
        [sys.executable, str(path), "--help"], cwd=tmp_path, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage:")
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []
