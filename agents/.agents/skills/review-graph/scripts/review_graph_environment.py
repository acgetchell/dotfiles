"""Check the installed helper's origin before retaining any runtime resources."""

import argparse
import base64
import hashlib
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ORIGIN_FILE = "python-origin.json"
_PACKAGE = "research_repo_tools"


def _installed_package() -> tuple[importlib.metadata.Distribution, Path]:
    spec = importlib.util.find_spec(_PACKAGE)
    if spec is None or spec.origin is None:
        msg = "review runtime requires the installed research-repo-tools dependency"
        raise ValueError(msg)
    try:
        distribution = importlib.metadata.distribution("research-repo-tools")
    except importlib.metadata.PackageNotFoundError as error:
        msg = "review helper import has no installed research-repo-tools distribution metadata"
        raise ValueError(msg) from error
    direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    if direct_url.get("dir_info", {}).get("editable"):
        msg = "review helper origin is an editable research-repo-tools installation; use an isolated packaged helper"
        raise ValueError(msg)
    origin = Path(spec.origin).resolve()
    entries = [entry for entry in distribution.files or () if str(entry) == f"{_PACKAGE}/__init__.py"]
    if len(entries) != 1 or Path(str(distribution.locate_file(entries[0]))).resolve() != origin:
        msg = "review helper import origin does not match its installed distribution RECORD"
        raise ValueError(msg)
    entry = entries[0]
    if entry.hash is None or entry.hash.mode != "sha256":
        msg = "review helper distribution requires a SHA-256 RECORD for its package origin"
        raise ValueError(msg)
    actual = base64.urlsafe_b64encode(hashlib.sha256(origin.read_bytes()).digest()).decode().rstrip("=")
    if actual != entry.hash.value:
        msg = "review helper package origin differs from its installed distribution RECORD"
        raise ValueError(msg)
    return distribution, origin


def _check_isolation(repository: Path, prefix: Path, executable: Path) -> None:
    if sys.prefix == sys.base_prefix or prefix.is_relative_to(repository) or executable.is_relative_to(repository):
        msg = "isolated helper requires a separate virtual environment outside the reviewed repository"
        raise ValueError(msg)
    # uv sets VIRTUAL_ENV to the newly selected helper; it is not evidence of
    # reuse. Check actual paths here; the launch clears discovery selectors.
    if not sys.flags.ignore_environment or not sys.flags.no_user_site:
        msg = "isolated helper requires Python -E -s to ignore Python environment selectors and user site packages"
        raise ValueError(msg)


def capture_python_origin(repository: Path, helper_version: str | None = None) -> dict[str, Any]:
    """Verify package provenance and, when requested, an independent helper environment."""
    prefix, executable = Path(sys.prefix).resolve(), Path(sys.executable).absolute()
    if helper_version is not None:
        _check_isolation(repository.resolve(), prefix, executable)
    distribution, package = _installed_package()
    site = Path(str(distribution.locate_file(""))).resolve()
    if (helper_version is not None and not site.is_relative_to(prefix)) or not package.is_relative_to(site):
        msg = "review helper distribution/import must belong to the executing Python environment"
        raise ValueError(msg)
    if helper_version is not None and distribution.version != helper_version:
        raise ValueError(f"review helper requires research-repo-tools=={helper_version}, found {distribution.version}")
    return {
        "helper_version": helper_version,
        "executable": str(executable),
        "prefix": str(prefix),
        "package": str(package),
        "distribution_root": str(site),
        "version": distribution.version,
        "record_digest": "sha256:" + hashlib.sha256((distribution.read_text("RECORD") or "").encode()).hexdigest(),
    }


def verify_helper_environment(origin: dict[str, Any]) -> None:
    """Keep an isolated run bound to its original environment, even for shared Python binaries."""
    if origin["helper_version"] is None:
        return
    if str(Path(sys.executable).absolute()) != origin["executable"] or str(Path(sys.prefix).resolve()) != origin["prefix"]:
        msg = "frozen isolated helper requires its original interpreter invocation and environment"
        raise ValueError(msg)
    if not sys.flags.ignore_environment or not sys.flags.no_user_site:
        msg = "frozen isolated helper requires Python -E -s"
        raise ValueError(msg)


def check_retained_origin(destination: Path, helper_version: str | None) -> None:
    """Never retrofit an isolation claim or a new version onto an existing runtime."""
    if helper_version is None:
        return
    path = destination / ORIGIN_FILE
    if not path.is_file() or json.loads(path.read_bytes())["helper_version"] != helper_version:
        msg = "frozen runtime helper origin policy cannot change; retain its evidence and report the setup blocker"
        raise ValueError(msg)


def main() -> int:
    """Print a read-only provenance probe without importing graph runtime dependencies."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--helper-version", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(capture_python_origin(args.repository, args.helper_version), sort_keys=True))
    except (OSError, ValueError) as error:
        print(f"review helper origin: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
