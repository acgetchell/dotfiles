"""Use a real editable package to test the disposable container's cached restoration."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from linux_review import source_identity

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT.parent / "editable fixture"
LEGACY_HELPER_VERSION = "0.2.9"
LEGACY_HELPER_RECEIPT = ROOT / "target/legacy-helper-origin.json"


def run(argv: list[str], *, cwd: Path = ROOT, environment: dict[str, str] | None = None, expected: int = 0) -> subprocess.CompletedProcess[str]:
    """Exercise a real command and report unexpected statuses with local fixture output."""
    result = subprocess.run(argv, cwd=cwd, env=environment, capture_output=True, text=True, check=False, timeout=600)  # noqa: S603 - fixed test commands.
    if result.returncode != expected:
        raise ValueError(f"Fixture command {argv[0]}: expected {expected}, got {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result


def legacy_helper_origin() -> str:
    """Verify the frozen helper through the real graph provenance check."""
    python = Path(os.environ["DOTFILES_REVIEW_PREFIX"]) / "helper/bin/python"
    return run(
        [
            str(python),
            "-E",
            "-s",
            "agents/.agents/skills/review-graph/scripts/review_graph_environment.py",
            "--repository",
            str(ROOT),
            "--helper-version",
            LEGACY_HELPER_VERSION,
        ]
    ).stdout


def prepare(uv: str, git: str) -> None:
    """Provision ordinary published build inputs and retain them for disconnected tests."""
    legacy = Path(os.environ["DOTFILES_REVIEW_PREFIX"]) / "helper"
    run([uv, "venv", "--no-project", "--no-config", "--python", sys.executable, str(legacy)])
    run([uv, "pip", "install", "--no-config", "--python", str(legacy / "bin/python"), "--link-mode", "copy", f"research-repo-tools=={LEGACY_HELPER_VERSION}"])
    LEGACY_HELPER_RECEIPT.write_text(legacy_helper_origin())
    FIXTURE.mkdir()
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    setuptools = next(item for item in metadata["dependency-groups"]["build"] if isinstance(item, str) and item.startswith("setuptools=="))
    (FIXTURE / "pyproject.toml").write_text(
        '[project]\nname="cloud-editable-fixture"\nversion="1.0.0"\nrequires-python=">=3.15"\n'
        "[build-system]\nrequires=[" + json.dumps(setuptools) + ']\nbuild-backend="setuptools.build_meta"\n'
        "[dependency-groups]\ndev=[]\n[tool.uv]\nrequired-version=" + json.dumps(metadata["tool"]["uv"]["required-version"]) + "\n"
    )
    package = FIXTURE / "src/cloud_editable_fixture"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('VALUE = "preserved source"\n')
    (FIXTURE / ".gitignore").write_text(".venv/\n*.egg-info/\nbuild/\n__pycache__/\n")
    shutil.copy2(ROOT / ".python-version", FIXTURE)
    run([uv, "lock"], cwd=FIXTURE)
    for arguments in (["init", "-q"], ["add", "."], ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixture"]):
        run([git, *arguments], cwd=FIXTURE)
    inventory = (ROOT / "profiles/cloud.toml").read_text()
    fixture_entry = f'\n[[repository]]\nname="editable-fixture"\npath={json.dumps(str(FIXTURE))}\ngroups=["dev"]\n'
    (ROOT / "target/rebuild-inventory.toml").write_text(inventory.replace('path = ".."', f"path = {json.dumps(str(ROOT))}") + fixture_entry)
    (ROOT / "target/fixture-inventory.toml").write_text("schema_version=1\n" + fixture_entry)


def installed_version() -> str:
    """Probe installed metadata and import the actual editable source."""
    result = run(
        [
            str(FIXTURE / ".venv/bin/python"),
            "-c",
            (
                "import importlib.metadata as m; from cloud_editable_fixture import VALUE; "
                "assert VALUE == 'preserved source'; print(m.version('cloud-editable-fixture'))"
            ),
        ]
    )
    return result.stdout.strip()


def verify() -> None:
    """Restore metadata, accept changed locked source, reject stale locks and absent caches."""
    before = source_identity(FIXTURE)
    metadata = list((FIXTURE / ".venv/lib").glob("python*/site-packages/cloud_editable_fixture-*.dist-info"))
    if len(metadata) != 1:
        msg = "Expected one installed editable fixture distribution"
        raise ValueError(msg)
    shutil.rmtree(metadata[0])
    startup = ["bash", "bin/cloud-profile.sh", "startup", "--inventory", "target/fixture-inventory.toml"]
    run(startup)
    if installed_version() != "1.0.0" or before != source_identity(FIXTURE):
        msg = "Editable metadata recovery changed source or failed to restore the declared version"
        raise ValueError(msg)
    project = FIXTURE / "pyproject.toml"
    project.write_text(project.read_text().replace('version="1.0.0"', 'version="1.0.1"'))
    uv = shutil.which("uv")
    if uv is None:
        msg = "Missing fixture uv"
        raise ValueError(msg)
    run([uv, "lock", "--offline"], cwd=FIXTURE)
    changed = source_identity(FIXTURE)
    run(startup)
    if installed_version() != "1.0.1" or changed != source_identity(FIXTURE):
        msg = "Changed-checkout restoration did not preserve the new locked source"
        raise ValueError(msg)
    supported = project.read_bytes()
    project.write_bytes(supported.replace(b"1.0.1", b"1.0.2"))
    stale = source_identity(FIXTURE)
    run(startup, expected=2)
    if source_identity(FIXTURE) != stale:
        msg = "Startup rewrote an invalid source/lock combination"
        raise ValueError(msg)
    project.write_bytes(supported)
    shutil.rmtree(FIXTURE / ".venv")
    # Keep the interpreter but deny all package/build cache; the container has no network.
    empty = ROOT / "target/empty-cache"
    empty.mkdir()
    run(startup, environment={**os.environ, "UV_CACHE_DIR": str(empty)}, expected=2)
    run(startup)
    if installed_version() != "1.0.1" or source_identity(FIXTURE) != changed:
        msg = "Retry after missing-cache failure did not preserve source and restore the package"
        raise ValueError(msg)
    verify_skills_only()
    print("Offline rebuild: editable recovery, changed source, stale lock, absent cache, retry, and skills-only checks passed")


def verify_skills_only() -> None:
    """Install twice into an isolated discovery root and preserve conflicts."""
    if legacy_helper_origin() != LEGACY_HELPER_RECEIPT.read_text():
        msg = "Profile upgrade changed the frozen helper's origin"
        raise ValueError(msg)
    destination = ROOT / "target/skills-only"
    skills = [sys.executable, "scripts/skills_install.py", "install", "--destination", str(destination)]
    run(skills)
    run(skills)
    collision = destination / "review-graph"
    collision.unlink()
    collision.mkdir()
    (collision / "keep").write_text("preserve")
    run(skills, expected=2)
    if (collision / "keep").read_text() != "preserve":
        msg = "Skills-only conflict changed existing content"
        raise ValueError(msg)


def main() -> int:
    """Refuse accidental use outside the deliberately named disposable container home."""
    if Path.home() != Path("/home/rebuild") or ROOT.parent != Path("/workspace"):
        msg = "This integration fixture runs only inside the disposable rebuild image"
        raise ValueError(msg)
    if sys.argv[1:] == ["prepare"]:
        uv, git = shutil.which("uv"), shutil.which("git")
        if uv is None or git is None:
            msg = "Missing fixture tools"
            raise ValueError(msg)
        prepare(uv, git)
    elif sys.argv[1:] == ["verify"]:
        verify()
    else:
        msg = "Use prepare or verify"
        raise ValueError(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
