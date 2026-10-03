"""Regressions for the Actions policy shared by local checks and repository settings."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from check_workflow_allowlist import allowed_repositories, check_workflow, workflow_references

REPOSITORY = Path(__file__).resolve().parents[1]
POLICY = REPOSITORY / ".github/settings/actions-selected.json"
SHA = "1111111111111111111111111111111111111111"
HEADER = "name: Test\non: workflow_dispatch\njobs:\n  check:\n"


@pytest.mark.parametrize(
    "body",
    [
        "    runs-on: ubuntu-latest\n    steps:\n      - name: Action\n        uses: {reference}\n",
        "    runs-on: ubuntu-latest\n    steps:\n      - uses: {reference}\n",
        "    runs-on: ubuntu-latest\n    steps:\n      - uses: '{reference}'\n",
        '    runs-on: ubuntu-latest\n    steps:\n      - "uses": "{reference}"\n',
        "    runs-on: ubuntu-latest\n    steps:\n      - uses: >-\n          {reference}\n",
        "    uses: {reference}\n",
        "    'uses': '{reference}'\n",
        "    uses: >-\n      {reference}\n",
    ],
)
def test_supported_yaml_forms_check_the_same_reference(tmp_path: Path, body: str) -> None:
    workflow = tmp_path / "workflow.yml"
    allowed = allowed_repositories(POLICY)
    approved = f"acgetchell/research-repo-tools/.github/workflows/dependabot-approve.yml@{SHA}"
    workflow.write_text(HEADER + body.format(reference=approved))
    assert check_workflow(workflow, allowed) == []
    workflow.write_text(HEADER + body.format(reference=approved.replace("acgetchell/", "unapproved/")))
    findings = check_workflow(workflow, allowed)
    assert len(findings) == 1
    assert "unapproved/research-repo-tools/.github/workflows/dependabot-approve.yml" in findings[0]


def test_actual_caller_mutation_is_rejected(tmp_path: Path) -> None:
    caller = REPOSITORY / ".github/workflows/dependabot-auto-merge.yml"
    allowed = allowed_repositories(POLICY)
    assert check_workflow(caller, allowed) == []
    changed = tmp_path / caller.name
    changed.write_text(caller.read_text().replace("acgetchell/research-repo-tools", "unapproved/example"))
    assert len(check_workflow(changed, allowed)) == 1


def test_settings_file_is_the_allowlist_authority(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(HEADER + f"    uses: dependabot/fetch-metadata@{SHA}\n")
    assert check_workflow(workflow, allowed_repositories(POLICY)) == []
    policy = json.loads(POLICY.read_text())
    policy["patterns_allowed"].remove("dependabot/fetch-metadata@*")
    changed = tmp_path / "policy.json"
    changed.write_text(json.dumps(policy))
    assert len(check_workflow(workflow, allowed_repositories(changed))) == 1


def test_local_and_container_actions_and_nonreference_uses_values_are_outside_policy(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        HEADER + "    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: ./.github/actions/local\n      - uses: docker://ubuntu:24.04\n"
        "      - run: echo hello\n        env:\n          uses: an ordinary variable\n"
    )
    assert check_workflow(workflow, allowed_repositories(POLICY)) == []


def test_yaml_aliases_are_checked_at_each_use() -> None:
    source = HEADER + f"    runs-on: ubuntu-latest\n    steps:\n      - &step\n        uses: unapproved/example@{SHA}\n      - *step\n"
    assert len(workflow_references(source)) == 2


@pytest.mark.parametrize(
    "source",
    [
        "jobs: {}\njobs: {}\n",
        "jobs: []\n",
        HEADER + "    steps: wrong\n",
        HEADER + "    uses: [wrong]\n",
        HEADER + "    uses: allowed/action@sha\n    uses: other/action@sha\n",
        HEADER + "    <<: {uses: hidden/action@sha}\n",
        HEADER + "    uses: [unterminated\n",
    ],
)
def test_invalid_workflows_fail_closed(source: str) -> None:
    with pytest.raises((ValueError, yaml.YAMLError)):
        workflow_references(source)


@pytest.mark.parametrize(
    "change",
    [
        {"github_owned_allowed": True},
        {"verified_allowed": True},
        {"patterns_allowed": []},
        {"patterns_allowed": ["actions/*"]},
        {"patterns_allowed": ["actions/checkout@main"]},
        {"patterns_allowed": [False]},
    ],
)
def test_unsupported_policy_cannot_silently_expand_access(tmp_path: Path, change: dict[str, object]) -> None:
    policy = json.loads(POLICY.read_text()) | change
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy))
    with pytest.raises(ValueError, match="Actions policy"):
        allowed_repositories(path)


def test_cli_reports_findings_and_parse_failures(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    command = [sys.executable, str(REPOSITORY / "scripts/check_workflow_allowlist.py"), "--policy", str(POLICY), str(workflow)]
    workflow.write_text(HEADER + f"    uses: unapproved/example/.github/workflows/test.yml@{SHA}\n")
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)  # noqa: S603
    assert result.returncode == 1
    assert f"{workflow}:5:" in result.stderr
    assert result.stdout == ""
    workflow.write_text("jobs: [unterminated")
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)  # noqa: S603
    assert result.returncode == 2
    assert "workflow allowlist:" in result.stderr
