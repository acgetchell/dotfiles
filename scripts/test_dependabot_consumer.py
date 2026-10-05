"""Check dotfiles' privileged workflow boundary and consumer policy."""

import json
import re
from pathlib import Path

import yaml

REPOSITORY = Path(__file__).resolve().parents[1]


def test_caller_is_pinned_and_has_no_pr_execution_or_forwarded_secrets() -> None:
    caller = yaml.safe_load((REPOSITORY / ".github/workflows/dependabot-auto-merge.yml").read_text())
    # PyYAML's YAML 1.1 loader represents the Actions `on` key as True.
    assert caller[True] == {"pull_request_target": {"types": ["opened", "reopened", "ready_for_review", "synchronize"], "branches": ["main"]}}
    assert caller["permissions"] == {}
    assert set(caller["jobs"]) == {"approve-and-enable-auto-merge"}
    job = caller["jobs"]["approve-and-enable-auto-merge"]
    assert set(job) == {"permissions", "uses", "with"}
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    workflow, revision = job["uses"].split("@")
    assert workflow == "acgetchell/research-repo-tools/.github/workflows/dependabot-approve.yml"
    assert re.fullmatch(r"[0-9a-f]{40}", revision)
    assert set(job["with"]) == {"repository", "policy"}
    assert job["with"]["repository"] == "acgetchell/dotfiles"


def test_policy_covers_only_configured_ecosystems_and_exact_dependency_files() -> None:
    caller = yaml.safe_load((REPOSITORY / ".github/workflows/dependabot-auto-merge.yml").read_text())
    policy = json.loads(caller["jobs"]["approve-and-enable-auto-merge"]["with"]["policy"])
    dependabot = yaml.safe_load((REPOSITORY / ".github/dependabot.yml").read_text())
    ecosystems = {update["package-ecosystem"].replace("-", "_") for update in dependabot["updates"]}
    assert set(policy) == ecosystems == {"uv", "github_actions"}
    assert policy["uv"] == {"files": ["pyproject.toml", "uv.lock"]}
    action_paths = {
        str(path.relative_to(REPOSITORY))
        for pattern in (".github/workflows/*.yml", ".github/workflows/*.yaml", ".github/actions/**/action.yml", ".github/actions/**/action.yaml")
        for path in REPOSITORY.glob(pattern)
    }
    assert policy["github_actions"] == {"files": sorted(action_paths)}


def test_post_merge_ci_dispatch_and_restricted_actions_settings() -> None:
    ci = yaml.safe_load((REPOSITORY / ".github/workflows/ci.yml").read_text())
    assert set(ci[True]) == {"workflow_dispatch", "pull_request", "push"}
    assert ci["permissions"] == {"contents": "read"}
    settings = REPOSITORY / ".github/settings"
    permissions = json.loads((settings / "actions-workflow-permissions.json").read_text())
    assert permissions == {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": True}
    selected = json.loads((settings / "actions-selected.json").read_text())
    assert selected["github_owned_allowed"] is False
    assert selected["verified_allowed"] is False
    assert {"dependabot/fetch-metadata@*", "acgetchell/research-repo-tools/.github/workflows/dependabot-approve.yml@*"} <= set(selected["patterns_allowed"])


def test_main_ruleset_preserves_merge_gates_and_bypass_policy() -> None:
    ruleset = json.loads((REPOSITORY / ".github/settings/main-ruleset.json").read_text())
    assert ruleset["enforcement"] == "active"
    assert ruleset["conditions"] == {"ref_name": {"exclude": [], "include": ["~DEFAULT_BRANCH"]}}
    assert ruleset["bypass_actors"] == [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}]
    rules = {rule["type"]: rule.get("parameters", {}) for rule in ruleset["rules"]}
    assert set(rules) == {"deletion", "non_fast_forward", "pull_request", "required_status_checks"}
    assert rules["pull_request"]["required_approving_review_count"] == 1
    assert rules["pull_request"]["dismiss_stale_reviews_on_push"] is True
    assert rules["pull_request"]["required_review_thread_resolution"] is True
    assert rules["required_status_checks"]["strict_required_status_checks_policy"] is True
    assert rules["required_status_checks"]["required_status_checks"] == [
        {"context": "verify", "integration_id": 15368},
        {"context": "CodeRabbit", "integration_id": 347564},
        {"context": "Linux portable review", "integration_id": 15368},
    ]
