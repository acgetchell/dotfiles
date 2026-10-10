"""Consumer contracts for the published checker and dotfiles' Actions policy."""

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPOSITORY = Path(__file__).resolve().parents[1]
POLICY = REPOSITORY / ".github/settings/actions-selected.json"
WORKFLOWS = REPOSITORY / ".github/workflows"
SHA = "1111111111111111111111111111111111111111"


def run_allowlist(*workflows: Path, policy: Path = POLICY) -> subprocess.CompletedProcess[str]:
    """Exercise the installed distribution through its isolated public CLI."""
    return subprocess.run(  # noqa: S603 - fixed installed module and explicit consumer inputs.
        [sys.executable, "-I", "-m", "research_repo_tools", "--root", str(REPOSITORY), "actions", "allowlist", "--policy", str(policy), *map(str, workflows)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_committed_workflows_pass_without_mutation() -> None:
    paths = [POLICY, *WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]
    before = {path: path.read_bytes() for path in paths}
    result = run_allowlist(WORKFLOWS)
    assert result.returncode == 0, result.stderr
    assert "External Actions allowlist passed" in result.stdout
    assert before == {path: path.read_bytes() for path in paths}


@pytest.mark.parametrize(
    ("name", "approved"),
    [("ci.yml", "actions/checkout"), ("dependabot-auto-merge.yml", "acgetchell/research-repo-tools/.github/workflows/dependabot-approve.yml")],
)
def test_actual_workflow_mutations_fail_with_source_locations(tmp_path: Path, name: str, approved: str) -> None:
    source = (WORKFLOWS / name).read_text()
    assert approved + "@" in source
    workflow = tmp_path / name
    changed = source.replace(approved + "@", "unapproved/example@", 1)
    workflow.write_text(changed)
    expected_line = next(number for number, line in enumerate(changed.splitlines(), start=1) if "unapproved/example@" in line)

    result = run_allowlist(workflow)

    assert result.returncode == 1
    assert f"{workflow}:{expected_line}:" in result.stderr
    assert "unapproved/example@*" in result.stderr
    assert "passed" not in result.stdout
    assert workflow.read_text() == changed


@pytest.mark.parametrize("reference", ["dependabot/fetch-metadata", "acgetchell/research-repo-tools/.github/workflows/dependabot-approve.yml"])
def test_committed_policy_is_authoritative_for_approved_integrations(tmp_path: Path, reference: str) -> None:
    workflow = tmp_path / "workflow.yml"
    if reference == "dependabot/fetch-metadata":
        workflow.write_text(f"jobs:\n  metadata:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: {reference}@{SHA}\n")
    else:
        workflow.write_bytes((WORKFLOWS / "dependabot-auto-merge.yml").read_bytes())
    assert run_allowlist(workflow).returncode == 0
    policy = json.loads(POLICY.read_text())
    policy["patterns_allowed"].remove(reference + "@*")
    changed = tmp_path / "selected.json"
    changed.write_text(json.dumps(policy))

    result = run_allowlist(workflow, policy=changed)

    assert result.returncode == 1
    assert reference + "@*" in result.stderr


def test_recipe_and_ci_keep_the_shared_allowlist_gate() -> None:
    just = shutil.which("just")
    assert just is not None
    result = subprocess.run(  # noqa: S603 - inspect the real recipe without executing validators.
        [just, "--dry-run", "github-actions-check"], cwd=REPOSITORY, check=True, capture_output=True, text=True, timeout=30
    )
    commands = [shlex.split(line) for line in result.stderr.splitlines() if "research-repo-tools actions allowlist" in line]
    assert commands == [
        [
            "uv",
            "run",
            "--locked",
            "--group",
            "dev",
            "research-repo-tools",
            "actions",
            "allowlist",
            "--policy",
            ".github/settings/actions-selected.json",
            ".github/workflows",
        ]
    ]
    assert "scripts/check_workflow_allowlist.py" not in result.stderr
    recipe_graph = json.loads(
        subprocess.run(  # noqa: S603
            [just, "--dump", "--dump-format", "json"], cwd=REPOSITORY, check=True, capture_output=True, text=True, timeout=30
        ).stdout
    )
    assert any(dependency["recipe"] == "check" for dependency in recipe_graph["recipes"]["ci"]["dependencies"])
    assert any(dependency["recipe"] == "github-actions-check" for dependency in recipe_graph["recipes"]["check"]["dependencies"])
    ci = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    assert any("just ci" in step.get("run", "") for step in ci["jobs"]["verify"]["steps"])
