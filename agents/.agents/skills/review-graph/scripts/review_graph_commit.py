"""Proof and reconciliation for the optional authorized commit/CI handoff."""

import json
import re
import shlex
import shutil
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

from capture_scope import _run_git, _scope_data, _update_part
from review_graph_git import _source_discovery_command, metadata_audit_blockers
from review_graph_integrity import canonical_json, digest_bytes
from review_graph_reuse import CommitHandoffTransition, regular_file_fingerprint, source_snapshot

if TYPE_CHECKING:
    from review_graph_plan import GraphPlan
    from review_graph_reuse import ExternalMetadataTransition


def verify_commit_transition(transition: CommitHandoffTransition) -> None:
    """Replay path, boundary, authorization, and retained-history identities."""
    verify_commit_identity(transition)
    proof = transition.commit_handoff
    if not proof.get("preserved_files") or not proof.get("native_ci"):
        msg = "commit handoff requires retained history and an exact-commit native obligation"
        raise ValueError(msg)
    retained = {}
    for item in proof["preserved_files"]:
        path = Path(item["path"])
        if path.resolve() != path or path.is_symlink() or not path.is_file() or digest_bytes(path.read_bytes()) != item["digest"]:
            raise ValueError(f"commit handoff history missing or changed: {path}")
        retained[path.name] = path.read_bytes()
    declarations = json.loads(retained["reconciliation.json"])
    if any(proof[key] != declarations[key] for key in ("authorization", "native_ci")):
        msg = "commit handoff policy differs from immutable reconciliation history"
        raise ValueError(msg)
    for policy in proof["preserved_evidence"].values():
        declared = declarations[policy["kind"]].get(policy["node_id"])
        metadata = json.loads(retained[policy["node_id"] + ".metadata_path"])
        if policy["policy"] != declared or policy["record_digest"] != digest_bytes(canonical_json(metadata["normalized_record"]).encode()):
            msg = "preserved commit evidence differs from its immutable reconciliation history"
            raise ValueError(msg)
    for key, snapshot in (("previous_capture", transition.before), ("new_capture", transition.after)):
        if source_snapshot(json.loads(retained[key + ".json"])) != snapshot:
            msg = "commit handoff capture differs from retained history"
            raise ValueError(msg)
    _verify_retained_records(proof, retained)


def _verify_retained_records(proof: dict[str, Any], retained: dict[str, bytes]) -> None:
    """Bind native replacement and record mappings to the original archived plan."""
    original_plan = json.loads(retained["plan.json"])
    native_units = {unit["node_id"]: unit for unit in original_plan["coalesced_validation_units"] if unit["node_id"] in proof["native_ci"]}
    if canonical_json(proof["previous_native_units"]) != canonical_json(native_units):
        msg = "native replacement differs from its retained execution identity"
        raise ValueError(msg)
    original_records = [json.loads(content)["normalized_record"] for name, content in retained.items() if name.endswith(".metadata_path")]
    if proof["source_records"] != {record["evidence_id"]: digest_bytes(canonical_json(record).encode()) for record in original_records}:
        msg = "commit source records differ from original immutable evidence"
        raise ValueError(msg)


def verify_commit_identity(transition: CommitHandoffTransition) -> None:
    """Check identity and scope before publishing any history files."""
    before, after = transition.before, transition.after
    stable = ("repository_root", "capture_mode", "base_ref", "merge_base", "requested_paths", "repository_path_fingerprints", "repository_symlink_paths")
    if before.capture_mode not in {"baseline", "worktree"} or any(getattr(before, key) != getattr(after, key) for key in stable):
        msg = "commit handoff requires identical complete paths, modes, and repository boundaries in baseline/worktree scope"
        raise ValueError(msg)
    if before.head == after.head or not bool(after.branch):
        msg = "commit handoff requires a new commit on a named branch"
        raise ValueError(msg)
    proof = transition.commit_handoff
    authorization = proof["authorization"]
    if (
        authorization.get("operation") != "branch-commit"
        or authorization.get("repository_root") != before.repository_root
        or authorization.get("branch") != after.branch
        or authorization.get("source_state") != list(before.source_state)
        or not isinstance(authorization.get("user_authorization"), str)
        or not authorization["user_authorization"].strip()
        or proof.get("parent_commit") != before.head
        or proof.get("commit") != after.head
    ):
        msg = "commit handoff requires explicit user authorization for this source, repository, and branch"
        raise ValueError(msg)


def verify_live_commit(previous: dict[str, Any], current: dict[str, Any]) -> str:
    """Independently capture the clean committed tree and require a direct descendant."""
    before, after = source_snapshot(previous), source_snapshot(current)
    before.verify()
    after.verify()
    git = shutil.which("git")
    if git is None:
        msg = "commit handoff requires Git"
        raise ValueError(msg)
    root = Path(after.repository_root)
    observed = _scope_data(git, root, after.capture_mode, after.base_ref, after.requested_paths)
    if source_snapshot(observed) != after:
        msg = "commit handoff live capture differs from supplied new_capture"
        raise ValueError(msg)
    # A scoped status misses uncommitted files elsewhere in the repository.
    if _run_git(git, root, ("status", "--porcelain=v1", "-z", "--untracked-files=all")):
        msg = "commit handoff requires a clean complete repository after committing"
        raise ValueError(msg)
    parents = _run_git(git, root, ("rev-list", "--parents", "-n", "1", after.head)).decode().split()
    if parents != [after.head, before.head]:
        msg = "commit handoff must be a single direct child of the captured HEAD; merges and rebases require replanning"
        raise ValueError(msg)
    # Git's clean status can hide assume-unchanged/skip-worktree and filtered bytes.
    # Compare every committed blob and mode to the captured path identity.
    if _committed_path_fingerprints(git, root, after.head) != dict(after.repository_path_fingerprints):
        msg = "committed tree bytes or modes differ from the complete reviewed path identities"
        raise ValueError(msg)
    return before.head


def _committed_path_fingerprints(git: str, root: Path, head: str) -> dict[str, str]:
    """Fingerprint Git blob bytes using the same framing as source capture."""
    committed = {}
    for entry in _run_git(git, root, ("ls-tree", "-r", "-z", head)).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        path = raw_path.decode("utf-8", "surrogateescape")
        if kind != b"blob" or mode not in {b"100644", b"100755", b"120000"}:
            msg = "commit handoff cannot prove submodule tree identities; replan required"
            raise ValueError(msg)
        content = _run_git(git, root, ("cat-file", "blob", oid.decode()))
        if mode == b"120000":
            digest = sha256()
            for label, value in (("path", raw_path), ("mode", mode), ("symlink-target", content)):
                _update_part(digest, label, value)
            committed[path] = digest.hexdigest()
        else:
            committed[path] = regular_file_fingerprint(path, content, executable=mode == b"100755")
    return committed


def commit_node_reasons(mode: str, record: dict[str, Any], transition: CommitHandoffTransition) -> list[dict[str, str]]:
    """Reuse only a reconciled immutable record; default to a fresh execution."""
    proof = transition.commit_handoff
    if mode == "audit":
        return metadata_audit_blockers(record, transition)
    policy = proof.get("preserved_evidence", {}).get(record.get("evidence_id"))
    if policy is not None and policy["record_digest"] == digest_bytes(canonical_json(record).encode()):
        return []
    return [{"reason_code": f"{mode}-commit-policy", "reason": "No verified source-only reconciliation for this exact immutable evidence."}]


def reconciliation_policy(
    document: dict[str, Any], records: dict[str, dict[str, Any]], entries: dict[str, dict[str, Any]], transition: ExternalMetadataTransition
) -> dict[str, Any]:
    """Bind explicit execution/comparison declarations to accepted evidence identities."""
    preserved = {}
    for node_id, policy in document.get("local_validation", {}).items():
        record = records.get(node_id, {})
        unit = entries.get(node_id, {}).get("dispatch", {}).get("validation_unit")
        if (
            unit is None
            or record.get("status") != "passed"
            or policy.get("git_dependencies") != []
            or policy.get("execution_identity") != unit
            or not policy.get("reason", "").strip()
            or policy.get("environment_unchanged") is not True
            or any(re.search(r"\bgit\b", command) for command in unit["commands"])
        ):
            msg = "local validation reuse requires passed evidence, exact execution identity, unchanged environment, and explicit source-only rationale"
            raise ValueError(msg)
        preserved[record["evidence_id"]] = {
            "record_digest": digest_bytes(canonical_json(record).encode()),
            "policy": policy,
            "node_id": node_id,
            "kind": "local_validation",
        }
    for node_id, policy in document.get("independent_reviews", {}).items():
        record = records.get(node_id, {})
        dispatch = entries.get(node_id, {}).get("dispatch", {})
        # A free-form target alone cannot identify the comparison revision.
        if (
            dispatch.get("mode") != "independent-review"
            or record.get("status") not in {"completed", "no-findings"}
            or policy.get("change_target") != dispatch["change_target"]
            or policy.get("comparison_commit") != transition.before.head
            or not policy.get("reason", "").strip()
            or "commands_executed" not in record
            or not _unchanged_comparison(dispatch["change_target"], transition.before.head)
        ):
            msg = "independent review reuse requires its original change target and captured comparison commit"
            raise ValueError(msg)
        if blockers := metadata_audit_blockers(record, transition):
            raise ValueError("independent review requires current Git-sensitive inspection: " + canonical_json(blockers))
        preserved[record["evidence_id"]] = {
            "record_digest": digest_bytes(canonical_json(record).encode()),
            "policy": policy,
            "node_id": node_id,
            "kind": "independent_reviews",
        }
    return preserved


def _unchanged_comparison(target: str, head: str) -> bool:
    """Prove a local worktree comparison against its captured immutable HEAD."""
    try:
        words = shlex.split(target)
    except ValueError:
        return False
    options = words[: words.index("--")] if "--" in words else words
    if {"--cached", "--staged"} & set(options) or not {"HEAD", head} & set(options):
        return False
    return _source_discovery_command(shlex.join(["HEAD" if word == head else word for word in words]))


def pin_independent_rechecks(plan: GraphPlan, transition: CommitHandoffTransition) -> GraphPlan:
    """Keep fresh reviews on the original comparison even after HEAD moves."""
    preserved = {item["node_id"] for item in transition.commit_handoff["preserved_evidence"].values()}
    nodes = []
    for node in plan.actual_worker_nodes:
        if node.mode == "independent-review" and node.node_id not in preserved:
            target = node.change_target or ""
            if not _unchanged_comparison(target, transition.before.head):
                msg = "commit handoff cannot pin the independent comparison target; replan required"
                raise ValueError(msg)
            words = shlex.split(target)
            boundary = words.index("--") if "--" in words else len(words)
            pinned = [transition.before.head if word == "HEAD" else word for word in words[:boundary]]
            node = replace(node, change_target=shlex.join([*pinned, *words[boundary:]]))
        nodes.append(node)
    return replace(plan, actual_worker_nodes=tuple(nodes))


def native_target(transitions: tuple[ExternalMetadataTransition, ...], node_id: str) -> dict[str, Any] | None:
    """Find the latest exact commit obligation in a composed metadata chain."""
    for transition in reversed(transitions):
        if isinstance(transition, CommitHandoffTransition) and node_id in transition.commit_handoff["native_ci"]:
            return {**transition.commit_handoff["native_ci"][node_id], "commit": transition.after.head}
    return None


def verify_native_results(payload: dict[str, Any], target: dict[str, Any] | None) -> None:
    """Require all named native targets to succeed on the exact new commit."""
    if target is None or payload["status"] != "passed":
        return
    results = payload.get("native_ci", [])
    expected = {(item["name"], item["target"]) for item in target["checks"]}
    actual = {(item["name"], item["target"]) for item in results}
    if (
        actual != expected
        or len(results) != len(expected)
        or any(item["head_sha"] != target["commit"] or item["conclusion"] != "success" or not item["url"].startswith("https://") for item in results)
    ):
        msg = "native CI requires successful results for every exact-commit check and native target"
        raise ValueError(msg)


def replacement_native_units(document: dict[str, Any], plan: GraphPlan, lifecycle: dict[str, str], head: str) -> GraphPlan:
    """Replace only pending native executions, retaining logical requirement ownership."""
    targets = document["native_ci"]
    units = {unit.node_id: unit for unit in plan.coalesced_validation_units}
    if not targets or not set(targets) <= units.keys():
        msg = "commit handoff requires existing native validation node IDs"
        raise ValueError(msg)
    for node_id, target in targets.items():
        commands = target["commands"]
        checks = target["checks"]
        if (
            lifecycle.get(node_id, "pending") not in {"pending", "blocked"}
            or not commands
            or len(commands) != len(units[node_id].working_directories)
            or any(re.search(rf"(?<![0-9a-f]){re.escape(head)}(?![0-9a-f])", command) is None for command in commands)
            or not checks
            or len({(item["name"], item["target"]) for item in checks}) != len(checks)
            or node_id in document.get("local_validation", {})
        ):
            msg = "native replacement requires pending/blocked checks, unique targets, and commands naming the new exact commit"
            raise ValueError(msg)
        units[node_id] = replace(units[node_id], commands=tuple(commands), planning_blocker=None)
    return replace(plan, coalesced_validation_units=tuple(units.values()))


def history_files(document: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, bytes]:
    """Retain both raw captures and the original lifecycle/journal/dispatch history."""
    result = {name + ".json": canonical_json(document[name]).encode() for name in ("previous_capture", "new_capture", "plan")}
    for field in ("journal_path", "dispatches_path"):
        result[field] = Path(document[field]).read_bytes()
    result["reconciliation.json"] = canonical_json(
        {key: document.get(key, {}) for key in ("authorization", "local_validation", "independent_reviews", "native_ci", "external_metadata_transitions")}
    ).encode()
    for node_id, source in sources.items():
        metadata = json.loads(Path(source["metadata_path"]).read_bytes())
        for key, path in {**source, "worker_payload_path": metadata.get("worker_payload_path")}.items():
            if path:
                result[f"{node_id}.{key}"] = Path(path).read_bytes()
    return result
