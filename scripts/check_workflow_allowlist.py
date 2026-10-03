"""Check step and reusable-workflow references against the committed Actions policy."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import cast

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode


class WorkflowPolicyError(ValueError):
    """The workflow or committed allowlist cannot satisfy the supported policy."""


def allowed_repositories(path: Path) -> frozenset[str]:
    """Read the supported exact-repository, any-revision policy without widening it."""
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("github_owned_allowed") is not False or policy.get("verified_allowed") is not False:
        message = "Actions policy must explicitly disable github_owned_allowed and verified_allowed"
        raise WorkflowPolicyError(message)
    patterns = policy.get("patterns_allowed")
    if not isinstance(patterns, list) or not patterns:
        message = "Actions policy must contain a nonempty patterns_allowed list"
        raise WorkflowPolicyError(message)
    repositories: set[str] = set()
    for pattern in patterns:
        if not isinstance(pattern, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@\*", pattern):
            message = "Actions policy supports only exact owner/repo[/path]@* entries; review other policy forms before enabling them"
            raise WorkflowPolicyError(message)
        repositories.add(pattern.removesuffix("@*"))
    return frozenset(repositories)


def mapping(node: Node | None) -> dict[str, Node]:
    """Read a YAML mapping without silently dropping duplicate or nonscalar keys."""
    if not isinstance(node, MappingNode):
        message = "expected a workflow mapping"
        raise WorkflowPolicyError(message)
    result: dict[str, Node] = {}
    for key, value in node.value:
        if not isinstance(key, ScalarNode) or key.value in result or key.value == "<<":
            message = "workflow mappings require unique scalar keys and no merge keys"
            raise WorkflowPolicyError(message)
        result[key.value] = value
    return result


def reference(node: Node) -> tuple[int, str]:
    """Keep each reference's source line for actionable diagnostics."""
    if not isinstance(node, ScalarNode) or not node.value.strip() or node.start_mark is None:
        message = "uses must contain a nonempty scalar reference"
        raise WorkflowPolicyError(message)
    # PyYAML's composer supplies these fields but its node classes lack annotations.
    line = cast("int", node.start_mark.line)
    value = cast("str", node.value)
    return line + 1, value.strip()


def workflow_references(source: str) -> list[tuple[int, str]]:
    """Inspect YAML structure so quoting, anchors, and step shorthand retain meaning."""
    workflow = mapping(yaml.compose(source, Loader=yaml.BaseLoader))
    jobs = mapping(workflow.get("jobs"))
    references = []
    for job_node in jobs.values():
        job = mapping(job_node)
        if "uses" in job:
            references.append(reference(job["uses"]))
        if "steps" not in job:
            continue
        steps = job["steps"]
        if not isinstance(steps, SequenceNode):
            message = "job steps must be a sequence"
            raise WorkflowPolicyError(message)
        for step_node in steps.value:
            step = mapping(step_node)
            if "uses" in step:
                references.append(reference(step["uses"]))
    return references


def check_workflow(path: Path, allowed: frozenset[str]) -> list[str]:
    """Report unapproved repository references; actionlint owns full workflow syntax."""
    findings = []
    for line, value in workflow_references(path.read_text(encoding="utf-8")):
        # Local and container actions are outside the external repository allowlist.
        if value.startswith(("./", "docker://")):
            continue
        repository, separator, revision = value.partition("@")
        if repository not in allowed or not separator or not revision:
            findings.append(f"{path}:{line}: unapproved external reference {value!r}; update the Actions policy deliberately")
    return findings


def main() -> int:
    """Check explicitly selected workflows, failing on invalid policy or YAML."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("workflows", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        allowed = allowed_repositories(args.policy)
        findings = [finding for path in args.workflows for finding in check_workflow(path, allowed)]
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"workflow allowlist: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding, file=sys.stderr)
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
