"""Freeze executable review resources and recover a run without editing evidence."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import runpy
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from review_graph_execution import CONTEXT_FILE, capture_execution_context, command_prefix, verify_execution_context

_MANIFEST = "runtime-manifest.json"
_REFERENCE = "runtime-reference.json"
_SCRIPT_ROOT = Path(__file__).resolve().parent
_VERIFIED: set[Path] = set()


def _object(raw: object, fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(raw, dict) or set(raw) != fields:
        msg = f"{label} requires exactly {sorted(fields)}"
        raise ValueError(msg)
    return {key: value for key, value in raw.items() if isinstance(key, str)}


def _text(raw: object, label: str) -> str:
    if not isinstance(raw, str) or not raw:
        msg = f"{label} must be a nonempty string"
        raise ValueError(msg)
    return raw


def _digest_value(raw: object) -> str:
    value = _text(raw, "runtime digest")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        msg = "runtime digest must be a SHA-256 identity"
        raise ValueError(msg)
    return value


def _require_inventory(raw: object) -> None:
    if not isinstance(raw, tuple) or any(not isinstance(pair, tuple) or len(pair) != 2 or any(not isinstance(value, str) for value in pair) for pair in raw):
        msg = "runtime resource inventory must be immutable path/digest pairs"
        raise TypeError(msg)


@dataclass(frozen=True, slots=True)
class RuntimeReference:
    """A parsed absolute manifest path and immutable byte identity."""

    path: Path
    digest: str

    def __post_init__(self) -> None:
        """Reject unsafe paths before reading any referenced resource."""
        if not self.path.is_absolute() or self.path.resolve() != self.path:
            msg = "runtime manifest must be absolute and must not traverse symlinks"
            raise ValueError(msg)
        _digest_value(self.digest)

    @classmethod
    def parse(cls, raw: object) -> RuntimeReference:
        """Parse the saved reference without coercing transport values."""
        data = _object(raw, {"path", "digest"}, "runtime reference")
        return cls(Path(_text(data["path"], "runtime path")), _digest_value(data["digest"]))

    def as_raw(self) -> dict[str, str]:
        """Serialize only an already valid reference."""
        return {"path": str(self.path), "digest": self.digest}


@dataclass(frozen=True, slots=True)
class InterpreterIdentity:
    """The pinned executable and interpreter version."""

    path: str
    digest: str
    version: str

    def __post_init__(self) -> None:
        """Reject incomplete interpreter identities."""
        _text(self.path, "interpreter path")
        _digest_value(self.digest)
        _text(self.version, "interpreter version")

    @classmethod
    def parse(cls, raw: object) -> InterpreterIdentity:
        """Parse the finite persisted interpreter shape."""
        data = _object(raw, {"path", "digest", "version"}, "runtime interpreter")
        return cls(_text(data["path"], "interpreter path"), _digest_value(data["digest"]), _text(data["version"], "interpreter version"))


@dataclass(frozen=True, slots=True)
class RuntimeManifest:
    """Validated immutable inventory of the frozen run's resources."""

    interpreter: InterpreterIdentity
    files: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        """Reject invalid identities and traversal before resource reads/writes."""
        _require_inventory(self.files)
        if not self.files or len({path for path, _digest in self.files}) != len(self.files):
            msg = "runtime manifest requires a nonempty unique inventory"
            raise ValueError(msg)
        for relative, digest in self.files:
            path = Path(relative)
            if path.is_absolute() or path.as_posix() != relative or not path.parts or set(path.parts) & {"..", "."} or relative in {_MANIFEST, _REFERENCE}:
                msg = f"runtime manifest resource must be a canonical relative path: {relative}"
                raise ValueError(msg)
            _digest_value(digest)

    @classmethod
    def parse(cls, raw: object) -> RuntimeManifest:
        """Parse all manifest fields before using any resource name."""
        data = _object(raw, {"format", "interpreter", "files"}, "runtime manifest")
        if data["format"] != "review-graph-runtime-v1":
            msg = "unsupported frozen runtime manifest format"
            raise ValueError(msg)
        files = data["files"]
        if not isinstance(files, dict):
            msg = "runtime manifest files must be an object"
            raise TypeError(msg)
        return cls(
            InterpreterIdentity.parse(data["interpreter"]),
            tuple(sorted((_text(path, "resource path"), _digest_value(digest)) for path, digest in files.items())),
        )

    def as_raw(self) -> dict[str, object]:
        """Serialize only an already parsed inventory."""
        return {"format": "review-graph-runtime-v1", "interpreter": asdict(self.interpreter), "files": dict(self.files)}


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _files(root: Path) -> dict[str, bytes]:
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in {"__pycache__", ".pytest_cache", ".git"} for part in relative.parts) or path.name.startswith("test_") or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            msg = f"runtime resources must not traverse symlinks: {path}"
            raise ValueError(msg)
        if path.is_file():
            files[relative.as_posix()] = path.read_bytes()
    return files


def _interpreter() -> InterpreterIdentity:
    executable = Path(sys.executable).resolve()
    return InterpreterIdentity(str(executable), _digest(executable.read_bytes()), sys.version)


def _read_reference(path: Path) -> RuntimeReference:
    return RuntimeReference.parse(json.loads(path.read_bytes()))


def verify_snapshot(reference: object) -> RuntimeManifest:
    """Verify the retained manifest, every resource, and the pinned interpreter."""
    parsed = reference if isinstance(reference, RuntimeReference) else RuntimeReference.parse(reference)
    path = parsed.path
    content = path.read_bytes()
    if _digest(content) != parsed.digest:
        msg = "frozen runtime manifest digest changed"
        raise ValueError(msg)
    manifest = RuntimeManifest.parse(json.loads(content))
    if manifest.interpreter != _interpreter():
        msg = "frozen runtime requires its original Python interpreter and version"
        raise ValueError(msg)
    root = path.parent
    for relative, identity in manifest.files:
        target = root / relative
        if not target.is_relative_to(root) or ".." in Path(relative).parts or target.resolve() != target or _digest(target.read_bytes()) != identity:
            msg = f"frozen runtime resource changed: {relative}"
            raise ValueError(msg)
    actual = set(_files(root)) - {_MANIFEST, _REFERENCE}
    if actual != {relative for relative, _identity in manifest.files}:
        msg = "frozen runtime resource inventory changed"
        raise ValueError(msg)
    if (root / CONTEXT_FILE).is_file():
        verify_execution_context(json.loads((root / CONTEXT_FILE).read_bytes()))
    return manifest


def _check_retained_context(destination: Path, execution_context: dict[str, object] | None) -> None:
    retained = destination / CONTEXT_FILE
    if execution_context is not None and (not retained.is_file() or json.loads(retained.read_bytes()) != execution_context):
        msg = "frozen runtime Python runner cannot change on retry"
        raise ValueError(msg)


def freeze_runtime(skill_root: Path, destination: Path, *, repository: Path, execution_context: dict[str, object] | None = None) -> dict[str, str]:
    """Atomically retain skills, routing, schemas, scripts and Python support code."""
    root, destination, repository = skill_root.resolve(), destination.absolute(), repository.resolve()
    if destination.resolve() != destination or destination.is_relative_to(repository) or repository.is_relative_to(destination):
        msg = "frozen runtime must be outside the reviewed repository without symlink traversal"
        raise ValueError(msg)
    reference_path = destination / _REFERENCE
    if reference_path.exists():
        reference = _read_reference(reference_path)
        verify_snapshot(reference)
        _check_retained_context(destination, execution_context)
        return reference.as_raw()
    spec = importlib.util.find_spec("research_repo_tools")
    if spec is None or spec.origin is None:
        msg = "review runtime requires the installed research-repo-tools dependency"
        raise ValueError(msg)
    dependency = Path(spec.origin).parent.resolve()
    skills, support = _files(root), _files(dependency)
    content = {"skills/" + path: data for path, data in skills.items()}
    content.update({"skills/review-graph/scripts/research_repo_tools/" + path: data for path, data in support.items()})
    if execution_context is not None:
        content[CONTEXT_FILE] = (json.dumps(execution_context, sort_keys=True, indent=2) + "\n").encode()
    # A concurrent edit during acquisition must not produce a mixed snapshot.
    if skills != _files(root) or support != _files(dependency):
        msg = "runtime resources changed during capture; retry startup"
        raise ValueError(msg)
    manifest = RuntimeManifest(_interpreter(), tuple(sorted((path, _digest(data)) for path, data in content.items())))
    manifest_bytes = (json.dumps(manifest.as_raw(), sort_keys=True, indent=2) + "\n").encode()
    reference = RuntimeReference(destination / _MANIFEST, _digest(manifest_bytes))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".review-runtime-", dir=destination.parent) as staging:
        staged = Path(staging) / "snapshot"
        for relative, data in {**content, _MANIFEST: manifest_bytes, _REFERENCE: (json.dumps(reference.as_raw(), sort_keys=True) + "\n").encode()}.items():
            path = staged / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o444)
        try:
            staged.rename(destination)
        except FileExistsError:
            saved = _read_reference(reference_path)
            verify_snapshot(saved)
            _check_retained_context(destination, execution_context)
            return saved.as_raw()
    verify_snapshot(reference)
    return reference.as_raw()


def verify_current_snapshot() -> dict[str, str] | None:
    """Check frozen CLI resources before parsing schemas or signed plans."""
    root = _SCRIPT_ROOT.parents[2]
    path = root / _REFERENCE
    if not path.is_file():
        return None
    reference = _read_reference(path)
    if root not in _VERIFIED:
        verify_snapshot(reference)
        _VERIFIED.add(root)
    context_path = root / CONTEXT_FILE
    if context_path.is_file() and Path.cwd().resolve() != Path(json.loads(context_path.read_bytes())["working_directory"]):
        msg = "run frozen helpers from the retained Python runner working_directory"
        raise ValueError(msg)
    sys.dont_write_bytecode = True
    return reference.as_raw()


def current_execution_context() -> dict[str, Any] | None:
    """Read the invocation policy from this runtime's verified resource inventory."""
    path = _SCRIPT_ROOT.parents[2] / CONTEXT_FILE
    if not path.is_file():
        return None
    reference = _read_reference(path.parent / _REFERENCE)
    verify_current_snapshot()
    manifest_bytes = reference.path.read_bytes()
    if _digest(manifest_bytes) != reference.digest:
        msg = "frozen runtime manifest digest changed"
        raise ValueError(msg)
    manifest = RuntimeManifest.parse(json.loads(manifest_bytes))
    content = path.read_bytes()
    if _digest(content) != dict(manifest.files)[CONTEXT_FILE]:
        msg = "frozen Python runner context changed during acquisition"
        raise ValueError(msg)
    context = json.loads(content)
    verify_execution_context(context)
    return context


def runtime_command(script: Path, *arguments: str) -> list[str]:
    """Use the retained repository runner for exact graph helper arguments."""
    prefix = command_prefix(current_execution_context())
    reference_path = _SCRIPT_ROOT.parents[2] / _REFERENCE
    if script.name == "run_timed.py" and reference_path.is_file():
        return [*prefix, str(Path(__file__).resolve()), "--reference", str(reference_path), "--script", "run_timed.py", "--", *arguments]
    return [*prefix, str(script.resolve()), *arguments]


def _check_resumed_runner(reference: RuntimeReference, runner_path: Path | None) -> None:
    if runner_path is None:
        return
    retained = json.loads((reference.path.parent / CONTEXT_FILE).read_bytes())
    proposed = capture_execution_context(json.loads(runner_path.read_bytes()), Path(retained["working_directory"]))
    if proposed != retained:
        msg = "frozen runtime Python runner cannot change on resume"
        raise ValueError(msg)


def bootstrap_frozen(args: argparse.Namespace, argv: list[str]) -> None:
    """Re-execute startup under the retained version; identical retries recover it."""
    if verify_current_snapshot() is not None:
        return
    roots = args.skill_root or [_SCRIPT_ROOT.parents[1]]
    if len(roots) != 1:
        msg = "frozen bootstrap requires one skill root containing its routing catalog"
        raise ValueError(msg)
    _check_portable_references(args.starter_config or args.input, roots[0])
    saved = json.loads(args.resume_from.read_bytes()) if args.resume_from is not None else {}
    if not isinstance(saved, dict):
        msg = "saved bootstrap must be an object"
        raise TypeError(msg)
    if saved.get("runtime_snapshot") is not None:
        reference = RuntimeReference.parse(saved["runtime_snapshot"])
        verify_snapshot(reference)
        _check_resumed_runner(reference, args.python_runner)
    else:
        capture = json.loads(args.capture.read_bytes())
        if not isinstance(capture, dict):
            msg = "bootstrap capture must be an object"
            raise ValueError(msg)
        repository = Path(_text(capture.get("repository_root"), "captured repository root"))
        context = capture_execution_context(json.loads(args.python_runner.read_bytes()), repository) if args.python_runner else None
        reference = RuntimeReference.parse(
            freeze_runtime(roots[0], args.output.resolve().with_suffix(".runtime"), repository=repository, execution_context=context)
        )
    frozen = reference.path.parent / "skills"
    catalog = args.catalog.resolve().relative_to(roots[0].resolve())
    remapped = []
    arguments = iter(argv)
    for argument in arguments:
        if argument in {"--skill-root", "--catalog"}:
            if next(arguments, None) is None:
                msg = f"missing value for {argument}"
                raise ValueError(msg)
        elif not argument.startswith(("--skill-root=", "--catalog=")):
            remapped.append(argument)
    catalog_path = saved["materialization_input"]["routing_catalog_path"] if saved.get("runtime_snapshot") is not None else str(frozen / catalog)
    remapped.extend(("--skill-root", str(frozen), "--catalog", catalog_path))
    script = frozen / "review-graph/scripts/review_graph_bootstrap.py"
    os.execv(sys.executable, [sys.executable, "-B", str(script), *remapped])  # noqa: S606 - pinned interpreter and verified snapshot script.


def _check_absolute_reference(raw: str, skill_root: Path) -> None:
    root = skill_root.resolve()
    path = Path(raw)
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        msg = f"static reference is missing or outside the approved skill root: {raw}"
        raise ValueError(msg)
    # Resolve the configured root alias, but reject links within it.
    relative = path.relative_to(skill_root.absolute()) if path.is_relative_to(skill_root.absolute()) else path.relative_to(root)
    if root / relative != resolved:
        msg = f"static reference traverses a symlink: {raw}"
        raise ValueError(msg)
    msg = f"absolute static reference cannot survive runtime freezing: {raw}; use $SKILLS_ROOT/{relative.as_posix()} or {relative.as_posix()}"
    raise ValueError(msg)


def _check_portable_references(input_path: Path, skill_root: Path) -> None:
    """Reject unsupported absolute static references before creating a freeze."""

    def inspect(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                inspect(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in {"static_references", "required_static_references"} and isinstance(item, list):
                    for raw in item:
                        if isinstance(raw, str) and Path(raw).is_absolute():
                            _check_absolute_reference(raw, skill_root)
                inspect(item)

    inspect(json.loads(input_path.read_bytes()))


def main(argv: list[str] | None = None) -> int:
    """Run a retained script using only verified snapshot resources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True, help="retained runtime-reference.json")
    parser.add_argument(
        "--script", choices=("review_graph_bootstrap.py", "review_graph_runtime.py", "review_graph_plan.py", "capture_scope.py", "run_timed.py"), required=True
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        reference = _read_reference(args.reference)
        verify_snapshot(reference)
        context_path = reference.path.parent / CONTEXT_FILE
        if context_path.is_file() and Path.cwd().resolve() != Path(json.loads(context_path.read_bytes())["working_directory"]):
            msg = "run frozen helpers from the retained Python runner working_directory"
            raise ValueError(msg)
        scripts = reference.path.parent / "skills/review-graph/scripts"
        sys.path.insert(0, str(scripts))
        sys.dont_write_bytecode = True
        arguments = args.args[1:] if args.args[:1] == ["--"] else args.args
        script = scripts.parents[1] / "review-validator/scripts/run_timed.py" if args.script == "run_timed.py" else scripts / args.script
        sys.argv = [str(script), *arguments]
        runpy.run_path(sys.argv[0], run_name="__main__")
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
