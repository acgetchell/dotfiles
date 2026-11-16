"""Exercise the current public working files in a credential-free disposable Linux image."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from linux_review import SourceIdentity, source_identity

ROOT = Path(__file__).resolve().parents[1]


def snapshot(destination: Path) -> SourceIdentity:
    """Copy tracked working files; staging explicitly opts new files into the context."""
    before = source_identity(ROOT, include_untracked=False)
    git = shutil.which("git")
    if git is None:
        msg = "Git is required for read-only source selection"
        raise ValueError(msg)
    listing = subprocess.run(  # noqa: S603 - read-only enumeration; no archive, index, or branch mutation.
        [git, "ls-files", "--cached", "-z"], cwd=ROOT, capture_output=True, check=True, timeout=30
    ).stdout
    for name in sorted(set(listing.split(b"\0")) - {b""}):
        path = Path(os.fsdecode(name))
        if path.is_absolute() or ".." in path.parts or ".git" in path.parts or path.name.endswith(".local"):
            raise ValueError(f"Nonportable Docker source selection: {path}")
        source, target = ROOT / path, destination / path
        if not source.exists() and not source.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(source.readlink(), target_is_directory=source.is_dir())
        else:
            shutil.copy2(source, target)
    if before != source_identity(ROOT, include_untracked=False):
        msg = "Working files changed while preparing the rebuild snapshot; rerun"
        raise ValueError(msg)
    return before


def main() -> int:
    """Record exact source/image identities and both phase exit statuses."""
    docker = shutil.which("docker")
    if docker is None:
        msg = "Docker is required only for this disposable integration harness"
        raise ValueError(msg)
    artifacts = ROOT / "target/rebuild"
    artifacts.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix="ubuntu-", dir=artifacts))
    image = f"dotfiles-rebuild:{attempt.name}"
    report: dict[str, object] = {"status": "failed", "platform": "linux/amd64", "image_tag": image}
    try:
        with tempfile.TemporaryDirectory(prefix="dotfiles-rebuild-source-") as directory:
            source = Path(directory)
            report["source"] = snapshot(source)
            for phase, argv in (
                (
                    "provision",
                    [
                        docker,
                        "build",
                        "--platform",
                        "linux/amd64",
                        "--progress",
                        "plain",
                        "-f",
                        str(source / "tests/rebuild/Dockerfile"),
                        "-t",
                        image,
                        str(source),
                    ],
                ),
                ("offline", [docker, "run", "--rm", "--platform", "linux/amd64", "--network", "none", image]),
            ):
                print(f"Docker {phase}: {attempt / (phase + '.log')}", flush=True)
                with (attempt / f"{phase}.log").open("wb") as log:
                    result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=2400)  # noqa: S603 - owned disposable image.
                report[f"{phase}_exit_code"] = result.returncode
                if result.returncode:
                    return result.returncode
                if phase == "provision":
                    report["image_id"] = subprocess.run(  # noqa: S603 - public image identity.
                        [docker, "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True, text=True, check=True, timeout=30
                    ).stdout.strip()
        report["status"] = "passed"
        return 0
    finally:
        (attempt / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"Rebuild receipt: {attempt / 'receipt.json'}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
