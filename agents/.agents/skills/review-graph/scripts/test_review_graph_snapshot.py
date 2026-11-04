"""Snapshot verification reads content once and retains every integrity boundary."""

import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

import pytest
from review_graph_session import verify_snapshot


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


@pytest.fixture
def snapshot(tmp_path: Path) -> dict[str, str]:
    """Build independently hashed bytes for the verifier's public manifest format."""
    root = tmp_path / "snapshot"
    resource = root / "skills" / "nested"
    resource.mkdir(parents=True)
    files = {"skills/nested/source.py": b"before\n", "skills/nested/données.bin": b"\x00\xff\r\n"}
    for name, content in files.items():
        (root / name).write_bytes(content)
    executable = Path(sys.executable).resolve()
    manifest = {
        "format": "review-graph-runtime-v1",
        "interpreter": {"path": str(executable), "digest": _digest(executable.read_bytes()), "version": sys.version},
        "files": {name: _digest(content) for name, content in files.items()},
    }
    content = json.dumps(manifest).encode()
    path = root / "runtime-manifest.json"
    path.write_bytes(content)
    return {"path": str(path), "digest": _digest(content)}


def test_snapshot_verification_reads_each_resource_once_and_rechecks_changed_bytes(snapshot: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(snapshot["path"]).parent
    files = json.loads(Path(snapshot["path"]).read_bytes())["files"]
    resources = {root / name for name in files}
    reads: Counter[Path] = Counter()
    original_read = Path.read_bytes

    def read(path: Path) -> bytes:
        if path in resources:
            reads[path] += 1
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    assert dict(verify_snapshot(snapshot).files) == files
    assert reads == Counter(dict.fromkeys(resources, 1))
    source = root / "skills/nested/source.py"
    metadata = source.stat()
    source.write_bytes(b"after!\n")
    os.utime(source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    with pytest.raises(ValueError, match=r"resource changed: skills/nested/source\.py"):
        verify_snapshot(snapshot)
    assert reads[source] == 2


@pytest.mark.parametrize("damage", ["missing", "added", "relative-link", "absolute-link", "directory-link"])
def test_snapshot_verification_preserves_inventory_and_symlink_rejections(snapshot: dict[str, str], tmp_path: Path, damage: str) -> None:
    root = Path(snapshot["path"]).parent
    source = root / "skills/nested/source.py"
    if damage == "missing":
        source.unlink()
        with pytest.raises(FileNotFoundError):
            verify_snapshot(snapshot)
        return
    if damage == "added":
        (root / "unexpected.json").write_bytes(b"{}")
        expected = "resource inventory changed"
    elif damage == "directory-link":
        directory = source.parent
        retained = tmp_path / "retained"
        directory.rename(retained)
        directory.symlink_to(retained, target_is_directory=True)
        expected = "resource changed"
    else:
        target = root / "same-bytes.py"
        target.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(os.path.relpath(target, source.parent) if damage == "relative-link" else target)
        expected = "resource changed"
    with pytest.raises(ValueError, match=expected):
        verify_snapshot(snapshot)
