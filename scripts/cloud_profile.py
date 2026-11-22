"""Run locked repository environments through connected setup and offline restoration."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from linux_review import source_identity
from skills_install import SELECTORS

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import FrameType
    from typing import NoReturn

type Mode = Literal["provision", "startup", "doctor"]
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
ROOT = Path(__file__).resolve().parents[1]


def names(value: object, label: str) -> tuple[str, ...]:
    """Parse unique command-free identifiers from an inventory boundary."""
    if not isinstance(value, list) or any(not isinstance(item, str) or not NAME.fullmatch(item) for item in value):
        raise ValueError(f"{label} must be an array of simple names")
    result = tuple(str(item) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def immutable_tool_pairs(value: object) -> tuple[tuple[str, str], ...]:
    """Parse immutable direct-constructor input without trusting its annotation."""
    if not isinstance(value, tuple):
        msg = "Tools must be immutable provision/check recipe pairs"
        raise TypeError(msg)
    result = []
    for pair in value:
        if not isinstance(pair, tuple) or len(pair) != 2:
            msg = "Tools must be immutable provision/check recipe pairs"
            raise ValueError(msg)
        parsed = names(list(pair), "tool recipes")
        result.append((parsed[0], parsed[1]))
    return tuple(result)


def review_prefix() -> Path:
    """Locate persistent tools and the isolated dotfiles review environment."""
    prefix = Path(os.environ.get("DOTFILES_REVIEW_PREFIX", Path.home() / ".local/share/dotfiles-review"))
    if not prefix.is_absolute():
        msg = "DOTFILES_REVIEW_PREFIX must be absolute"
        raise ValueError(msg)
    return prefix


@dataclass(frozen=True, slots=True)
class RepositoryProfile:
    """An existing checkout with immutable environment and optional tool selections."""

    name: str
    path: Path
    groups: tuple[str, ...] = ("dev",)
    tools: tuple[tuple[str, str], ...] = ()
    review_environment: bool = False

    def __post_init__(self) -> None:
        """Reject invalid direct construction before any environment effects."""
        if not isinstance(self.name, str) or not NAME.fullmatch(self.name):
            msg = "Repository name must be a simple identifier"
            raise ValueError(msg)
        if not isinstance(self.path, Path) or not self.path.is_absolute() or not self.path.is_dir():
            msg = "Repository path must be an existing absolute directory"
            raise ValueError(msg)
        if type(self.review_environment) is not bool or (self.review_environment and self.path.resolve() != ROOT):
            msg = "Only this dotfiles checkout can select its private review environment"
            raise ValueError(msg)
        if not isinstance(self.groups, tuple) or names(list(self.groups), "groups") != self.groups:
            msg = "Repository groups must be immutable names"
            raise ValueError(msg)
        object.__setattr__(self, "tools", immutable_tool_pairs(self.tools))
        for filename in ("pyproject.toml", "uv.lock"):
            if not (self.path / filename).is_file():
                raise ValueError(f"{self.name}: missing {filename}")

    @property
    def environment(self) -> Path:
        """Use the consumer's own normal environment location."""
        if self.review_environment:
            return review_prefix() / "venv"
        return self.path / ".venv"


def parse_repository(raw: object, directory: Path) -> RepositoryProfile:
    """Parse the complete per-repository shape without executable shell text."""
    if not isinstance(raw, dict) or set(raw) - {"name", "path", "groups", "tools", "review-environment"} or not {"name", "path"} <= set(raw):
        msg = "Each repository needs name/path and only supported inventory fields"
        raise ValueError(msg)
    name, path = raw["name"], raw["path"]
    if not isinstance(name, str) or not isinstance(path, str) or not path.strip():
        msg = "Repository name/path must be nonempty strings"
        raise ValueError(msg)
    tools = raw.get("tools", [])
    if not isinstance(tools, list):
        msg = "tools must be an array of provision/check recipe pairs"
        raise TypeError(msg)
    pairs = tuple(names(pair, "tool recipes") for pair in tools)
    if any(len(pair) != 2 for pair in pairs):
        msg = "Each tool family needs a provision and a read-only check recipe"
        raise ValueError(msg)
    review = raw.get("review-environment", False)
    if type(review) is not bool:
        msg = "review-environment must be a boolean"
        raise TypeError(msg)
    return RepositoryProfile(
        name, (directory / Path(path).expanduser()).resolve(), names(raw.get("groups", ["dev"]), "groups"), tuple((pair[0], pair[1]) for pair in pairs), review
    )


def load_inventory(path: Path) -> tuple[tuple[RepositoryProfile, ...], str]:
    """Return profiles in inventory order and the SHA-256 hex digest of the file bytes.

    Resolve relative checkout paths from the inventory's directory. Reject repeated
    names, checkout paths, or environments before the caller starts provisioning.
    """
    content = path.read_bytes()
    raw = tomllib.loads(content.decode("utf-8"))
    if set(raw) != {"schema_version", "repository"} or type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        msg = "Inventory requires schema_version = 1 and repository entries"
        raise ValueError(msg)
    entries = raw["repository"]
    if not isinstance(entries, list) or not entries:
        msg = "Inventory must select at least one repository"
        raise ValueError(msg)
    repositories = tuple(parse_repository(entry, path.resolve().parent) for entry in entries)
    for values in ([item.name for item in repositories], [item.path for item in repositories], [item.environment.resolve() for item in repositories]):
        if len(set(values)) != len(values):
            msg = "Inventory repeats a repository name, checkout, or environment"
            raise ValueError(msg)
    return repositories, hashlib.sha256(content).hexdigest()


def environment_for(profile: RepositoryProfile, uv: Path, *, offline: bool) -> dict[str, str]:
    """Remove ambient selectors and make offline behavior explicit at every command."""
    environment = {key: value for key, value in os.environ.items() if key not in (*SELECTORS, "UV_NO_SYNC", "UV_OFFLINE", "UV_PYTHON_DOWNLOADS")}
    environment["UV_PROJECT_ENVIRONMENT"] = str(profile.environment)
    environment["PATH"] = str(uv.parent) + os.pathsep + environment.get("PATH", os.defpath)
    if offline:
        environment.update(UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never")
    if profile.review_environment:
        cache = Path(os.environ.get("DOTFILES_REVIEW_CACHE", Path.home() / ".cache/dotfiles-review"))
        environment["UV_CACHE_DIR"] = str(cache / "uv")
        environment["UV_PYTHON_INSTALL_DIR"] = str(profile.environment.parent / "python")
    return environment


def sync_arguments(profile: RepositoryProfile, mode: Mode) -> list[str]:
    """Let uv own lock validation and rebuild only locally editable distributions."""
    arguments = ["sync", "--locked"]
    for group in profile.groups:
        arguments.extend(("--group", group))
    if mode != "provision":
        arguments.extend(("--offline", "--no-python-downloads"))
    if mode == "doctor":
        arguments.append("--check")
    elif mode == "startup":
        lock = tomllib.loads((profile.path / "uv.lock").read_text(encoding="utf-8"))
        packages = lock.get("package", [])
        if not isinstance(packages, list):
            msg = "Lockfile package inventory must be an array"
            raise ValueError(msg)
        for package in packages:
            if not isinstance(package, dict) or not isinstance(package.get("source"), dict):
                msg = "Lockfile package requires a source table"
                raise TypeError(msg)
            if "editable" in package["source"]:
                selected = names([package.get("name")], "editable package")
                arguments.extend(("--reinstall-package", selected[0]))
    return arguments


@contextmanager
def environment_lock(environment: Path) -> Generator[None]:
    """Hold the lock for this resolved environment until the context exits.

    Raise ValueError immediately if another lifecycle command holds the lock.
    The lock file can persist between runs. Its open descriptor holds the lock.
    """
    if os.name != "posix":
        msg = "Cloud lifecycle requires macOS or Linux"
        raise ValueError(msg)
    import fcntl  # noqa: PLC0415 - import only after the supported-platform check.

    directory = Path.home() / ".cache/dotfiles-cloud/locks"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (hashlib.sha256(os.fsencode(environment.resolve())).hexdigest() + ".lock")
    with path.open("a") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            msg = "Environment is in use by another cloud lifecycle command; retry when it finishes"
            raise ValueError(msg) from None
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def execute(argv: list[str], profile: RepositoryProfile, mode: Mode, results: list[dict[str, object]], *, uv: Path) -> None:
    """Retain command outcomes without leaking child output or credentials into receipts."""
    if os.name != "posix":
        msg = "Cloud lifecycle requires macOS or Linux"
        raise ValueError(msg)
    with subprocess.Popen(  # noqa: S603 - fixed uv operations or explicitly selected repository recipes.
        argv,
        cwd=profile.path,
        env=environment_for(profile, uv, offline=mode != "provision"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    ) as child:
        try:
            stdout, stderr = child.communicate(timeout=900)
        except BaseException:
            # Stop descendants before releasing the environment lock on timeout/interruption.
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.communicate()
            results.append({"argv": argv, "exit_code": child.returncode, "interrupted": True})
            raise
    results.append(
        {"argv": argv, "exit_code": child.returncode, "stdout_sha256": hashlib.sha256(stdout).hexdigest(), "stderr_sha256": hashlib.sha256(stderr).hexdigest()}
    )
    if child.returncode:
        diagnostic = stderr.decode("utf-8", errors="replace").casefold()
        cause = "command failed; inspect the selected recipe"
        if "lockfile" in diagnostic and ("update" in diagnostic or "changed" in diagnostic):
            cause = "stale lockfile; reconcile it in the owning repository before provisioning"
        elif mode != "provision" and ("offline" in diagnostic or "cache" in diagnostic):
            cause = "offline restoration needs missing cache/build inputs; run connected provisioning"
        raise ValueError(f"{profile.name}: {cause} (exit {child.returncode})")


def uv_pin(path: Path, name: str) -> str:
    """Parse the owning repository's exact tool requirement before synchronization."""
    metadata = tomllib.loads((path / "pyproject.toml").read_text(encoding="utf-8"))
    tool = metadata.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    pin = uv.get("required-version") if isinstance(uv, dict) else None
    if not isinstance(pin, str) or not re.fullmatch(r"==\d+\.\d+\.\d+", pin):
        raise ValueError(f"{name}: provide its exact [tool.uv] required-version before running this lifecycle")
    return pin[2:]


def profile_uv() -> Path:
    """Locate the uv executable supplied by platform setup."""
    executable = shutil.which("uv")
    if executable is None:
        msg = "Profile uv is unavailable; run platform setup on a connected host"
        raise ValueError(msg)
    return Path(executable).absolute()


def checked_uv_version(uv: Path, pin: str, label: str, recovery: str) -> str:
    """Require an executable that identifies itself as the owning repo's exact uv."""
    try:
        version = subprocess.run([str(uv), "--version"], capture_output=True, check=True, timeout=10).stdout.decode("utf-8", errors="replace").strip()  # noqa: S603
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"{label} cannot run; {recovery}") from error
    if version.split()[:2] != ["uv", pin]:
        raise ValueError(f"{label} does not match required version {pin}; {recovery}")
    return version


def install_uv(uv: Path, pin: str, profile: RepositoryProfile, results: list[dict[str, object]]) -> str:
    """Stage a pinned native wheel and publish only its verified standalone executable."""
    bootstrap = profile_uv()
    uv.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=uv.parent) as stage:
        arguments = [
            "pip",
            "install",
            "--no-config",
            "--no-deps",
            "--only-binary",
            ":all:",
            "--no-python-downloads",
            "--python",
            sys.executable,
            "--link-mode",
            "copy",
            "--target",
            stage,
            f"uv=={pin}",
        ]
        try:
            execute([str(bootstrap), *arguments], profile, "provision", results, uv=bootstrap)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise ValueError(f"{profile.name}: could not provision uv {pin}; check the connected host's package index and retry") from error
        staged = Path(stage) / "bin/uv"
        version = checked_uv_version(staged, pin, f"{profile.name}: downloaded uv", "check the package index and retry connected provisioning")
        # Readers see a complete executable even when separate inventories provision the same pin.
        staged.replace(uv)
    return version


def select_uv(profile: RepositoryProfile, mode: Mode, pin: str, results: list[dict[str, object]]) -> tuple[Path, str]:
    """Use the profile uv for its pin and retained version-specific tools for other pins."""
    if pin == uv_pin(ROOT, "dotfiles"):
        uv = profile_uv()
        return uv, checked_uv_version(uv, pin, f"{profile.name}: profile uv", "run platform setup for the pinned profile uv")
    uv = review_prefix() / "uv" / pin / "uv"
    if uv.exists() or uv.is_symlink():
        recovery = f"restore the retained uv {pin} or remove the invalid executable and run connected cloud-provision"
        return uv, checked_uv_version(uv, pin, f"{profile.name}: retained uv", recovery)
    if mode != "provision":
        raise ValueError(f"{profile.name}: retained uv {pin} is missing; restore it or run connected cloud-provision")
    return uv, install_uv(uv, pin, profile, results)


def run_repository(profile: RepositoryProfile, mode: Mode, report: dict[str, object]) -> None:
    """Check pins and preserve checkout identity across synchronization and tool probes."""
    just = shutil.which("just")
    if profile.tools and just is None:
        raise ValueError(f"{profile.name}: Just is required for the selected tool recipes")
    pin = uv_pin(profile.path, profile.name)
    results: list[dict[str, object]] = []
    report.update(
        name=profile.name,
        uv_required_version=pin,
        commands=results,
        repository=str(profile.path),
        environment=str(profile.environment),
        lock_sha256=hashlib.sha256((profile.path / "uv.lock").read_bytes()).hexdigest(),
    )
    with environment_lock(profile.environment):
        before = source_identity(profile.path)
        report["source_before"] = before
        try:
            uv, version = select_uv(profile, mode, pin, results)
            report.update(uv=version, uv_executable=str(uv))
            arguments = sync_arguments(profile, mode)
            execute([str(uv), *arguments], profile, mode, results, uv=uv)
            if mode == "startup" and "--reinstall-package" in arguments:
                # A restored setuptools tree can create egg-info during the forced build,
                # changing uv's source timestamp. Reconcile once without forcing another
                # rebuild, then require the normal read-only health check to pass.
                execute([str(uv), *sync_arguments(profile, "provision"), "--offline", "--no-python-downloads"], profile, mode, results, uv=uv)
            for provision, check in profile.tools:
                if mode == "provision":
                    execute([str(just), provision], profile, mode, results, uv=uv)
                execute([str(just), check], profile, mode, results, uv=uv)
            if mode != "doctor":
                execute([str(uv), *sync_arguments(profile, "doctor")], profile, "doctor", results, uv=uv)
            if profile.review_environment:
                bash = shutil.which("bash")
                if bash is None:
                    msg = "Bash is required for the profile health check"
                    raise ValueError(msg)
                execute([bash, str(ROOT / "bin/setup-profile.sh"), "auto", "doctor"], profile, mode, results, uv=uv)
        finally:
            after = source_identity(profile.path)
            report["source_after"] = after
            if before != after:
                raise ValueError(f"{profile.name}: source or HEAD changed during lifecycle; preserve and inspect the changes")
    report["status"] = "passed"


def cancel_lifecycle(signum: int, _frame: FrameType | None) -> NoReturn:
    """Unwind child supervision and locks before publishing an interrupted receipt."""
    # Repeated termination requests must not interrupt child cleanup.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise SystemExit(128 + signum)


def main(argv: list[str] | None = None) -> int:
    """Write a private receipt for every attempt, including failures and interruptions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("provision", "startup", "doctor"))
    parser.add_argument("--inventory", type=Path, default=ROOT / "profiles/cloud.toml")
    parser.add_argument("--receipts", type=Path, default=ROOT / "target/cloud")
    args = parser.parse_args(argv)
    reports: list[dict[str, object]] = []
    report: dict[str, object] = {
        "schema_version": 1,
        "mode": args.mode,
        "status": "failed",
        "repositories": reports,
        "platform": platform.platform(),
        "architecture": platform.machine(),
    }
    try:
        args.receipts.mkdir(parents=True, exist_ok=True)
        attempt = Path(tempfile.mkdtemp(prefix=f"{args.mode}-", dir=args.receipts))
    except OSError:
        print("cloud profile: cannot create receipt directory", file=sys.stderr)
        return 2
    previous_handler = signal.signal(signal.SIGTERM, cancel_lifecycle)
    try:
        profiles, report["inventory_sha256"] = load_inventory(args.inventory)
        for profile in profiles:
            uv_pin(profile.path, profile.name)
            sync_arguments(profile, args.mode)
        for profile in profiles:
            entry: dict[str, object] = {"name": profile.name, "status": "failed"}
            reports.append(entry)
            run_repository(profile, args.mode, entry)
        report["status"] = "passed"
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        # Our validation errors contain public names; subprocess exceptions can contain captured private output.
        diagnostic = str(error) if isinstance(error, (ValueError, TypeError)) else f"{type(error).__name__}: prerequisite or command unavailable"
        report["diagnostic"] = diagnostic
        print(f"cloud profile: {diagnostic}", file=sys.stderr)
    except KeyboardInterrupt, SystemExit:
        report["diagnostic"] = "Lifecycle interrupted; child cleanup completed before releasing its environment lock"
        raise
    finally:
        try:
            (attempt / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"Cloud lifecycle receipt: {attempt / 'receipt.json'}")
        except OSError:
            report["status"] = "failed"
            print("cloud profile: cannot write lifecycle receipt", file=sys.stderr)
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
