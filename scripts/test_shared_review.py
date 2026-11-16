"""Consumer checks for dotfiles' public CodeRabbit recipes."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
GIT_LOCATION_VARIABLES = frozenset({"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES"})


def _consumer(tmp_path: Path, git: str, environment: dict[str, str]) -> tuple[Path, str]:
    """Give the real recipes their own refs, including on detached CI checkouts."""
    root = tmp_path / "review consumer ü"
    root.mkdir()
    for name in ("justfile", "pyproject.toml", "uv.lock", ".python-version", "AGENTS.md", ".coderabbit.yaml"):
        shutil.copy2(REPOSITORY / name, root / name)
    hooks = tmp_path / "empty-hooks"
    hooks.mkdir()
    for arguments in (
        ["init", "--initial-branch=main"],
        ["add", "."],
        ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture"],
        ["update-ref", "refs/remotes/origin/main", "HEAD"],
        ["checkout", "--detach", "--quiet"],
    ):
        subprocess.run(  # noqa: S603 - isolated fixture repository; never mutate the actual checkout.
            [git, "-C", str(root), "-c", f"core.hooksPath={hooks}", *arguments], env=environment, capture_output=True, text=True, check=True, timeout=30
        )
    head = subprocess.run(  # noqa: S603 - read the fixture's actual commit for the remote freshness response.
        [git, "-C", str(root), "rev-parse", "HEAD"], env=environment, capture_output=True, text=True, check=True, timeout=30
    ).stdout.strip()
    return root, head


@pytest.mark.parametrize(("recipe", "stale"), [(["review"], False), (["review", "main"], False), (["review-uncommitted"], False), (["review"], True)])
def test_review_recipe_preserves_scope_and_shared_exit_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recipe: list[str], stale: bool) -> None:
    caller_index = tmp_path / "caller-index"
    caller_index.write_bytes(b"preserve the caller's index")
    monkeypatch.setenv("GIT_INDEX_FILE", str(caller_index))
    # Git location overrides take precedence over -C, including in nested uv/just
    # commands. Keep every operation confined to the fixture repository.
    environment = {key: value for key, value in os.environ.items() if key.upper() not in GIT_LOCATION_VARIABLES}
    real_git = shutil.which("git")
    assert real_git is not None
    root, head = _consumer(tmp_path, real_git, environment)
    log = tmp_path / "review.json"
    executable = tmp_path / "coderabbit"
    executable.write_text(
        f"#!{sys.executable}\nimport json, sys\nfrom pathlib import Path\n"
        'if sys.argv[1:] == ["--version"]:\n    print("0.7.7")\n    raise SystemExit(0)\n'
        f"Path({str(log)!r}).write_text(json.dumps(sys.argv[1:]))\nraise SystemExit(23)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    # Model read-only Git inspection, including remote freshness for the default
    # base. Explicit local overrides retain their offline behavior.
    git_log = tmp_path / "git.jsonl"
    git = tmp_path / "git"
    git.write_text(
        f"#!{sys.executable}\nimport json, subprocess, sys\nfrom pathlib import Path\n"
        f"with Path({str(git_log)!r}).open('a') as stream:\n    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        'if sys.argv[1:] == ["--no-pager", "ls-remote", "--exit-code", "origin", "refs/heads/main"]:\n'
        f'    print({"b" * 40 if stale else head!r} + "\\trefs/heads/main")\n'
        # v0.2.9 binds the real worktree/index/config before dispatch. Delegate
        # only its read-only inventory, retaining the modeled remote freshness.
        'elif any(command in sys.argv[1:] for command in ("rev-parse", "ls-files", "ls-tree", "merge-base")) or '
        '("config" in sys.argv[1:] and "--list" in sys.argv[1:]):\n'
        f"    raise SystemExit(subprocess.run([{real_git!r}, *sys.argv[1:]], check=False).returncode)\n"
        'else:\n    raise SystemExit("unexpected Git operation")\n',
        encoding="utf-8",
    )
    git.chmod(0o755)
    just = shutil.which("just")
    assert just is not None
    environment = {
        **environment,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "UV_PROJECT_ENVIRONMENT": sys.prefix,
        "UV_CACHE_DIR": str(tmp_path / ".uv-cache"),
        "UV_OFFLINE": "1",
    }

    result = subprocess.run([just, *recipe], cwd=root, env=environment, capture_output=True, text=True, check=False, timeout=30)  # noqa: S603

    assert caller_index.read_bytes() == b"preserve the caller's index"
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
    assert str(root / "AGENTS.md") in arguments
    assert str(root / ".coderabbit.yaml") in arguments
    assert "--agent" in arguments
    assert "--include-untracked" in arguments
    assert "--use-credits" not in arguments
