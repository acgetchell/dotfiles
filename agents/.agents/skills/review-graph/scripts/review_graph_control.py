"""Issue immutable run control identities and share terminal authority across journals."""

import fcntl
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from review_graph_integrity import canonical_json, digest_bytes
from review_graph_lifecycle import ControlReference, RunControlBinding

if TYPE_CHECKING:
    from collections.abc import Generator


def read_control_file(path: Path) -> bytes:
    """Read only canonical regular paths, including their ancestor boundary."""
    if not path.is_absolute() or path.resolve() != path:
        msg = f"run control path must not traverse symlinks: {path}"
        raise ValueError(msg)
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            msg = f"run control path must be a regular file: {path}"
            raise ValueError(msg)
        stream = os.fdopen(descriptor, "rb")
        descriptor = -1
        with stream:
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _write_control_file(path: Path, document: dict[str, Any]) -> ControlReference:
    content = (canonical_json(document) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".control.", dir=path.parent)
    temporary = Path(name)
    created = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o444)
            os.fsync(stream.fileno())
        try:
            path.hardlink_to(temporary)
            created = True
        except FileExistsError:
            if read_control_file(path) != content:
                msg = f"refusing to overwrite non-identical run control identity: {path}"
                raise ValueError(msg) from None
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError, ValueError:
        if created:
            path.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return ControlReference(str(path), digest_bytes(content))


def _reference_document(reference: ControlReference) -> dict[str, Any]:
    content = read_control_file(Path(reference.path))
    if digest_bytes(content) != reference.digest:
        msg = "run control artifact differs from its immutable reference"
        raise ValueError(msg)
    document = json.loads(content)
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        msg = "run control artifact requires a versioned object"
        raise ValueError(msg)
    return document


def issue_run_control(origin: dict[str, Any], *, repository: Path, root: Path | None = None) -> RunControlBinding:
    """Initialize authority before a new plan is copied; replay a supplied root identically."""
    root = root.absolute() if root is not None else Path(tempfile.mkdtemp(prefix="review-graph-control-")).resolve()
    if root.resolve() != root:
        msg = "run control root must not traverse symlinks"
        raise ValueError(msg)
    repository = repository.resolve()
    if not repository.is_dir() or root.is_relative_to(repository) or repository.is_relative_to(root):
        msg = "run control initialization requires a real repository and an external control store"
        raise ValueError(msg)
    identity = _write_control_file(
        root / "identity.json", {"schema_version": 1, "origin_digest": digest_bytes(canonical_json(origin).encode()), "repository_root": str(repository)}
    )
    generation = _write_control_file(
        root / "generation-000.json",
        {
            "schema_version": 1,
            "identity": asdict(identity),
            "ordinal": 0,
            "parent": None,
            "policy": {key: value for key, value in origin["review_lifecycle"].items() if key != "run_control"},
        },
    )
    return RunControlBinding(identity, generation)


def require_run_control(binding: RunControlBinding | None) -> RunControlBinding:
    """Keep historical unbound transport readable without granting admission."""
    if binding is None:
        msg = "unbound review lifecycle cannot execute; initialize a current-format plan"
        raise ValueError(msg)
    return binding


def verify_run_control(
    binding: RunControlBinding | None, *, repository: Path | None = None, policy: dict[str, Any] | None = None, pending_generation: bool = False
) -> dict[str, Any]:
    """Verify shared authority without creating it for historical transport."""
    binding = require_run_control(binding)
    identity = _reference_document(binding.identity)
    recorded_repository = identity.get("repository_root")
    if (
        not isinstance(recorded_repository, str)
        or not Path(recorded_repository).is_absolute()
        or Path(recorded_repository).resolve() != Path(recorded_repository)
    ):
        msg = "run control identity requires its initialized repository_root"
        raise ValueError(msg)
    generation = _reference_document(binding.generation)
    root = Path(binding.identity.path).parent
    if (
        Path(binding.identity.path).name != "identity.json"
        or Path(binding.generation.path).parent != root
        or generation.get("identity") != asdict(binding.identity)
    ):
        msg = "run control generation differs from its shared identity"
        raise ValueError(msg)
    if type(generation.get("ordinal")) is not int or generation["ordinal"] < 0:
        msg = "run control generation requires a nonnegative ordinal"
        raise ValueError(msg)
    if generation["parent"] is not None and not pending_generation:
        parent = ControlReference.from_document(generation["parent"])
        prior = _reference_document(parent)
        marker = Path(parent.path).with_suffix(".extension.json")
        transition = json.loads(read_control_file(marker))
        if (
            prior.get("identity") != asdict(binding.identity)
            or prior.get("ordinal") != generation["ordinal"] - 1
            or not isinstance(transition, dict)
            or transition.get("next_generation") != asdict(binding.generation)
        ):
            msg = "run control generation lacks its committed parent extension"
            raise ValueError(msg)
    if policy is not None:
        policy = json.loads(canonical_json(policy))
        authority = generation.get("policy")
        if (
            not isinstance(authority, dict)
            or any(policy.get(key) != authority.get(key) for key in ("repair_budget", "budget_extensions"))
            or policy.get("repairs_completed", -1) < authority.get("repairs_completed", 0)
            or policy.get("comprehensive_restarts", [])[: len(authority.get("comprehensive_restarts", []))] != authority.get("comprehensive_restarts", [])
        ):
            msg = "review lifecycle differs from its authoritative control generation counters or history"
            raise ValueError(msg)
    if repository is not None and Path(recorded_repository) != repository.resolve():
        msg = "run control identity repository_root differs from the signed repository"
        raise ValueError(msg)
    if root.is_relative_to(Path(recorded_repository)) or Path(recorded_repository).is_relative_to(root):
        msg = "run control store must be outside the reviewed repository"
        raise ValueError(msg)
    return generation


def control_marker_paths(binding: RunControlBinding) -> tuple[Path, Path]:
    """Resolve run-wide user stopping before generation-specific budget exhaustion."""
    return Path(binding.identity.path).with_name("user-stop.json"), Path(binding.generation.path).with_suffix(".stop.json")


def extend_run_control(binding: RunControlBinding, policy: dict[str, Any], *, parent_result: str | None) -> RunControlBinding:
    """Issue an explicitly extended generation while retaining root stop authority."""
    original = verify_run_control(binding)
    generation = {
        "schema_version": 1,
        "identity": asdict(binding.identity),
        "ordinal": original["ordinal"] + 1,
        "parent": asdict(binding.generation),
        "parent_result": parent_result,
        "policy": {key: value for key, value in policy.items() if key != "run_control"},
    }
    name = "generation-" + digest_bytes(canonical_json(generation).encode())[7:23] + ".json"
    reference = _write_control_file(Path(binding.identity.path).with_name(name), generation)
    return RunControlBinding(binding.identity, reference)


@contextmanager
def run_control_lock(binding: RunControlBinding | None) -> Generator[None]:
    """Order terminal publication and admission across every journal of the run."""
    verify_run_control(binding)
    binding = require_run_control(binding)
    path = Path(binding.identity.path).with_name("admission.lock")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        msg = "run control admission lock must be a regular non-symlink file"
        raise ValueError(msg)
    with os.fdopen(descriptor, "a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
