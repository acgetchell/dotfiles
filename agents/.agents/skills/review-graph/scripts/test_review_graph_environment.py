"""Offline helper isolation with a same-version editable consumer and a real wheel."""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest
from review_graph_environment import ORIGIN_FILE, capture_python_origin
from review_graph_session import freeze_runtime
from test_review_graph_runtime import _baseline_mutation_fixture

SCRIPTS = Path(__file__).resolve().parent
VERSION = "0.2.3"
DIST = f"research_repo_tools-{VERSION}.dist-info"
SELECTORS = (
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "UV_PROJECT_ENVIRONMENT",
    "UV_PYTHON",
    "UV_PROJECT",
    "UV_WORKING_DIR",
    "UV_CONFIG_FILE",
    "UV_NO_CACHE",
    "UV_TARGET",
    "UV_PREFIX",
    "UV_SYSTEM_PYTHON",
    "UV_OVERRIDE",
    "PYTHONHOME",
)


def _run(argv: list[str], directory: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=directory, env=environment, text=True, capture_output=True, check=False, timeout=60)  # noqa: S603 - offline fixture commands.


def _wheel(directory: Path) -> Path:
    directory.mkdir()
    files = {
        "research_repo_tools/__init__.py": b"ORIGIN = 'packaged distribution'\n",
        f"{DIST}/METADATA": f"Metadata-Version: 2.1\nName: research-repo-tools\nVersion: {VERSION}\n".encode(),
        f"{DIST}/WHEEL": b"Wheel-Version: 1.0\nGenerator: review-graph-fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = []
    for name, content in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
        record.append(f"{name},sha256={digest},{len(content)}\n")
    files[f"{DIST}/RECORD"] = ("".join(record) + f"{DIST}/RECORD,,\n").encode()
    wheel = directory / f"research_repo_tools-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return wheel


def _editable(repository: Path, environment: dict[str, str]) -> Path:
    target = repository / ".venv"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(target)
    python = target / "bin/python"
    location = _run([str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], repository, environment)
    assert location.returncode == 0, location.stderr
    site = Path(location.stdout.strip())
    source = repository / "src/research_repo_tools"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("ORIGIN = 'unpublished editable consumer'\n")
    (site / "consumer.pth").write_text(str(source.parent) + "\n")
    metadata = site / DIST
    metadata.mkdir()
    (metadata / "METADATA").write_text(f"Metadata-Version: 2.1\nName: research-repo-tools\nVersion: {VERSION}\n")
    (metadata / "direct_url.json").write_text(json.dumps({"url": repository.as_uri(), "dir_info": {"editable": True}}))
    (metadata / "RECORD").write_text("")
    (repository / "pyproject.toml").write_text(f'[project]\nname = "research-repo-tools"\nversion = "{VERSION}"\n')
    (repository / ".python-version").write_text("3.9\n")
    return python


def _skills(directory: Path) -> Path:
    scripts = directory / "review-graph/scripts"
    scripts.mkdir(parents=True)
    for name in ("review_graph_session.py", "review_graph_environment.py", "review_graph_execution.py"):
        shutil.copyfile(SCRIPTS / name, scripts / name)
    (scripts / "capture_scope.py").write_text(
        "import json\nfrom pathlib import Path\nimport research_repo_tools\n"
        "from review_graph_session import runtime_command, verify_current_snapshot\n"
        "verify_current_snapshot()\n"
        "print(json.dumps({'marker': research_repo_tools.ORIGIN, 'command': runtime_command(Path(__file__))}))\n"
    )
    return directory


@pytest.mark.parametrize("active", [False, True])
def test_isolated_launch_selects_packaged_bytes_and_retains_environment(tmp_path: Path, active: bool) -> None:  # noqa: PLR0915 - complete offline provenance lifecycle.
    uv = shutil.which("uv")
    assert uv is not None
    repository = tmp_path / "consumer"
    repository.mkdir()
    environment = {key: value for key, value in os.environ.items() if not key.startswith(("UV_", "PYTHON")) and key not in SELECTORS}
    python = _editable(repository, environment)
    wheel = _wheel(tmp_path / "wheelhouse")
    skills = _skills(tmp_path / "skills")
    destination = tmp_path / "runtime"
    environment.update(UV_CACHE_DIR=str(tmp_path / "cache"), UV_OFFLINE="1", PYTHONPATH=str(repository / "src"))
    if active:
        environment.update({name: str(python.parent.parent) for name in ("VIRTUAL_ENV", "CONDA_PREFIX", "UV_PROJECT_ENVIRONMENT")})
        environment.update(UV_PYTHON=str(python), UV_PROJECT=str(repository), UV_WORKING_DIR=str(repository))
        environment["PATH"] = str(python.parent) + os.pathsep + environment["PATH"]
    query = "import json,sys,research_repo_tools; print(json.dumps([sys.executable,research_repo_tools.ORIGIN]))"
    # The old documented command really does satisfy ==0.2.3 from the editable checkout.
    old = _run(
        [
            uv,
            "run",
            "--no-project",
            "--python",
            f"{sys.version_info.major}.{sys.version_info.minor}",
            "--with",
            f"research-repo-tools=={VERSION}",
            "python",
            "-c",
            query,
        ],
        repository,
        environment,
    )
    assert old.returncode == 0, old.stderr
    assert json.loads(old.stdout) == [str(python), "unpublished editable consumer"]
    protected = {path: path.read_bytes() for path in repository.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    freeze = (
        f"import sys,json; sys.path.insert(0,{str(SCRIPTS)!r}); "
        "from pathlib import Path; from review_graph_session import freeze_runtime; "
        f"print(json.dumps(freeze_runtime(Path({str(skills)!r}),Path({str(destination)!r}),repository=Path({str(repository)!r}),helper_version={VERSION!r})))"
    )
    # Ambient selectors are explicit here, including values which would prevent Python startup.
    environment.update(PYTHONHOME=str(repository / "invalid-home"), UV_CONFIG_FILE=str(repository / "missing-uv.toml"), UV_NO_CACHE="1")
    env = shutil.which("env")
    assert env is not None
    launch = [env, *(argument for name in SELECTORS for argument in ("-u", name)), uv, "--no-config"]
    helper_root = tmp_path / "helper"
    helper_python = helper_root / "bin/python"
    created = _run([*launch, "venv", "--no-project", "--python", str(Path(sys.executable).resolve()), str(helper_root)], repository, environment)
    assert created.returncode == 0, created.stderr
    installed = _run(
        [
            *launch,
            "pip",
            "install",
            "--python",
            str(helper_python),
            "--link-mode",
            "copy",
            "--no-index",
            "--find-links",
            str(wheel.parent),
            f"research-repo-tools=={VERSION}",
        ],
        repository,
        environment,
    )
    assert installed.returncode == 0, installed.stderr
    result = _run([str(helper_python), "-E", "-s", "-c", freeze], repository, environment)
    assert result.returncode == 0, result.stderr
    reference = json.loads(result.stdout)
    origin = json.loads((destination / ORIGIN_FILE).read_bytes())
    helper = Path(origin["executable"])
    assert helper == helper_python
    assert helper.exists()
    assert Path(origin["prefix"]) != python.parent.parent
    assert not Path(origin["prefix"]).is_relative_to(repository)
    assert Path(origin["package"]).is_relative_to(Path(origin["prefix"]))
    assert origin["version"] == origin["helper_version"] == VERSION
    frozen_script = destination / "skills/review-graph/scripts/capture_scope.py"
    retained = _run([str(helper), "-E", "-s", str(frozen_script)], repository, environment)
    assert retained.returncode == 0, retained.stderr
    output = json.loads(retained.stdout)
    assert output == {"marker": "packaged distribution", "command": [str(helper), "-E", "-s", str(frozen_script)]}
    # Shared base executable bytes do not authorize switching to the consumer environment.
    switched = _run([str(python), "-E", "-s", str(frozen_script)], repository, environment)
    assert switched.returncode != 0
    assert "original interpreter invocation and environment" in switched.stderr
    # Consumer validation still runs in the editable consumer environment.
    consumer = _run([str(python), "-E", "-s", "-c", query], repository, environment)
    assert consumer.returncode == 0, consumer.stderr
    assert json.loads(consumer.stdout) == [str(python), "unpublished editable consumer"]
    assert {path: path.read_bytes() for path in repository.rglob("*") if path.is_file() and "__pycache__" not in path.parts} == protected
    manifest = json.loads(Path(reference["path"]).read_bytes())
    assert ORIGIN_FILE in manifest["files"]


def test_editable_origin_fails_before_freezing(tmp_path: Path) -> None:
    repository = tmp_path / "consumer"
    repository.mkdir()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
    python = _editable(repository, environment)
    destination = tmp_path / "runtime"
    script = (
        f"import sys; sys.path.insert(0,{str(SCRIPTS)!r}); from pathlib import Path; from review_graph_session import freeze_runtime; "
        f"freeze_runtime(Path({str(SCRIPTS.parent.parent)!r}),Path({str(destination)!r}),repository=Path({str(repository)!r}))"
    )
    result = _run([str(python), "-E", "-s", "-c", script], repository, environment)
    assert result.returncode != 0
    assert "editable research-repo-tools" in result.stderr
    assert not destination.exists()


def test_existing_runtime_cannot_be_relabelled_as_an_isolated_helper(tmp_path: Path) -> None:
    repository, skills, destination = tmp_path / "consumer", _skills(tmp_path / "skills"), tmp_path / "runtime"
    repository.mkdir()
    reference = freeze_runtime(skills, destination, repository=repository)
    protected = {path: path.read_bytes() for path in destination.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="helper origin policy cannot change"):
        freeze_runtime(skills, destination, repository=repository, helper_version=VERSION)
    assert {path: path.read_bytes() for path in destination.rglob("*") if path.is_file()} == protected
    assert reference["path"] == str(destination / "runtime-manifest.json")


def test_package_origin_shadowing_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import research_repo_tools  # noqa: PLC0415 - alter only the already imported module's spec for this probe.

    assert research_repo_tools.__spec__ is not None
    monkeypatch.setattr(research_repo_tools.__spec__, "origin", str(tmp_path / "research_repo_tools/__init__.py"))
    with pytest.raises(ValueError, match=r"does not match.*RECORD"):
        capture_python_origin(tmp_path)


@pytest.mark.parametrize("wrong_version", [False, True])
def test_bootstrap_checks_origin_before_fanout_and_preserves_flags(tmp_path: Path, wrong_version: bool) -> None:
    _git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    capture_path, input_path, output = (tmp_path / name for name in ("capture.json", "input.json", "bootstrap.json"))
    capture_path.write_text(json.dumps(capture))
    input_path.write_text(json.dumps(template))
    version = "0.0.0" if wrong_version else capture_python_origin(repository)["version"]
    command = [
        sys.executable,
        "-E",
        "-s",
        str(SCRIPTS / "review_graph_bootstrap.py"),
        "--helper-version",
        version,
        "--capture",
        str(capture_path),
        "--input",
        str(input_path),
        "--output",
        str(output),
    ]
    result = _run(command, repository, dict(os.environ))
    if wrong_version:
        assert result.returncode == 2
        assert "requires research-repo-tools==0.0.0" in result.stderr
        assert not output.exists()
        assert not output.with_suffix(".runtime").exists()
        return
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["next_command"][:3] == [sys.executable, "-E", "-s"]
    dispatched = _run(receipt["next_command"], repository, dict(os.environ))
    assert dispatched.returncode == 0, dispatched.stderr
    original = output.read_bytes()
    retry = _run(command, repository, dict(os.environ))
    assert retry.returncode == 0, retry.stderr
    assert output.read_bytes() == original
    changed = command.copy()
    changed[changed.index("--helper-version") + 1] = "0.0.0"
    rejected = _run(changed, repository, dict(os.environ))
    assert rejected.returncode == 2
    assert "helper origin policy cannot change" in rejected.stderr
    assert output.read_bytes() == original
