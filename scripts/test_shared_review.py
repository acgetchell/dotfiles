"""Consumer checks for dotfiles' public CodeRabbit recipes."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("recipe", "stale"), [(["review"], False), (["review", "main"], False), (["review-uncommitted"], False), (["review"], True)])
def test_review_recipe_preserves_scope_and_shared_exit_status(tmp_path: Path, recipe: list[str], stale: bool) -> None:
    log = tmp_path / "review.json"
    executable = tmp_path / "coderabbit"
    executable.write_text(
        f"#!{sys.executable}\nimport json, sys\nfrom pathlib import Path\nPath({str(log)!r}).write_text(json.dumps(sys.argv[1:]))\nraise SystemExit(23)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    # Model read-only Git inspection, including remote freshness for the default
    # base. Explicit local overrides retain their offline behavior.
    git_log = tmp_path / "git.jsonl"
    git = tmp_path / "git"
    git.write_text(
        f"#!{sys.executable}\nimport json, sys\nfrom pathlib import Path\n"
        f"with Path({str(git_log)!r}).open('a') as stream:\n    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        'if sys.argv[1:] == ["--no-pager", "ls-remote", "--exit-code", "origin", "refs/heads/main"]:\n'
        f'    print({"b" if stale else "a"!r} * 40 + "\\trefs/heads/main")\n'
        'elif sys.argv[1:-1] == ["--no-pager", "rev-parse", "--verify", "--end-of-options"] and '
        'sys.argv[-1] in {"main^{commit}", "refs/remotes/origin/main^{commit}"}:\n'
        '    print("a" * 40)\n'
        'else:\n    raise SystemExit("unexpected Git operation")\n',
        encoding="utf-8",
    )
    git.chmod(0o755)
    just = shutil.which("just")
    assert just is not None
    environment = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", "UV_OFFLINE": "1"}

    result = subprocess.run([just, *recipe], cwd=REPOSITORY, env=environment, capture_output=True, text=True, check=False, timeout=30)  # noqa: S603

    assert result.returncode != 0
    git_calls = [json.loads(line) for line in git_log.read_text().splitlines()] if git_log.exists() else []
    assert any("ls-remote" in call for call in git_calls) is (recipe == ["review"])
    if stale:
        assert "origin/main is stale" in result.stderr
        assert not log.exists()
        return
    assert "exit code 23" in result.stderr
    arguments = json.loads(log.read_text())
    assert ("--base=origin/main" in arguments) == (recipe == ["review"])
    assert ("--base=main" in arguments) == (recipe == ["review", "main"])
    assert ("--uncommitted" in arguments) == (recipe[0] == "review-uncommitted")
    assert str(REPOSITORY / "AGENTS.md") in arguments
    assert str(REPOSITORY / ".coderabbit.yaml") in arguments
