"""Consumer checks for dotfiles' public CodeRabbit recipes."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("recipe", [["review"], ["review", "main"], ["review-uncommitted"]])
def test_review_recipe_preserves_scope_and_shared_exit_status(tmp_path: Path, recipe: list[str]) -> None:
    log = tmp_path / "review.json"
    executable = tmp_path / "coderabbit"
    executable.write_text(
        f"#!{sys.executable}\nimport json, sys\nfrom pathlib import Path\nPath({str(log)!r}).write_text(json.dumps(sys.argv[1:]))\nraise SystemExit(23)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    # CI checkouts need not have a local main branch. Model only the read-only
    # resolver boundary, and reject remote lookups or any mutating command.
    git = tmp_path / "git"
    git.write_text(
        f"#!{sys.executable}\nimport sys\n"
        'if sys.argv[1:] != ["--no-pager", "rev-parse", "--verify", "--end-of-options", "main^{commit}"]:\n'
        '    raise SystemExit("unexpected Git operation")\n'
        'print("a" * 40)\n',
        encoding="utf-8",
    )
    git.chmod(0o755)
    just = shutil.which("just")
    assert just is not None
    environment = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", "UV_OFFLINE": "1"}

    result = subprocess.run([just, *recipe], cwd=REPOSITORY, env=environment, capture_output=True, text=True, check=False, timeout=30)  # noqa: S603

    assert result.returncode != 0
    assert "exit code 23" in result.stderr
    arguments = json.loads(log.read_text())
    assert ("--base=main" in arguments) == (recipe[0] == "review")
    assert ("--uncommitted" in arguments) == (recipe[0] == "review-uncommitted")
    assert str(REPOSITORY / "AGENTS.md") in arguments
    assert str(REPOSITORY / ".coderabbit.yaml") in arguments
