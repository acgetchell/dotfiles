"""Shared helper integration preserves graph identities and Python environments."""

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import venv
from typing import TYPE_CHECKING, Any

import capture_scope
import pytest
import review_graph_bootstrap as bootstrap
import review_graph_plan as plan
import review_graph_runtime as runtime
from review_graph_bootstrap import _capture_command
from review_graph_integrity import canonical_json, digest_bytes, digest_json
from review_graph_plan import _file_identity_digest
from review_graph_receipts import artifact_reference
from review_graph_usage import digest, parse_json
from test_capture_scope import _git, _init_repo
from test_review_graph_runtime import SKILL_ROOT, _baseline_capture, _sparse_plan_document, _worker_input_fixture

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("content", [b"", b"first\r\nsecond\n\xff\x00last\r"])
def test_shared_hashes_preserve_existing_exact_byte_artifact_identities(tmp_path: Path, content: bytes) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(content)
    expected = "sha256:" + hashlib.sha256(content).hexdigest()

    assert digest_bytes(content) == expected
    assert _file_identity_digest(str(artifact)) == expected
    assert artifact_reference(artifact) == {"path": str(artifact.resolve()), "digest": expected}
    assert artifact.read_bytes() == content


def test_shared_hashing_preserves_compact_ascii_json_without_a_final_newline() -> None:
    value = {"z": [1, True, None], "a": "é"}
    original_bytes = b'{"a":"\\u00e9","z":[1,true,null]}'
    expected = "sha256:" + hashlib.sha256(original_bytes).hexdigest()

    assert canonical_json(value).encode() == original_bytes
    assert digest_json(value) == digest(value) == expected
    assert digest_json({"a": "é", "z": (1, True, None)}) == expected


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_accounting_retains_nonfinite_rejection_with_shared_hashing(nonfinite: float) -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        digest({"cost": nonfinite})


@pytest.mark.parametrize(
    ("content", "error", "message"),
    [
        ('{"cost":1,"cost":2}', ValueError, "duplicate JSON field"),
        ('{"cost":NaN}', ValueError, "Out of range float"),
        ('{"cost":Infinity}', ValueError, "Out of range float"),
        ("[]", TypeError, "JSON input must be an object"),
    ],
)
def test_strict_accounting_parser_retains_malformed_input_rejection(content: str, error: type[ValueError | TypeError], message: str) -> None:
    with pytest.raises(error, match=message):
        parse_json(content)


@pytest.mark.parametrize("output", [b"", b"first\r\nsecond\n\xff\x00last\r"])
def test_shared_git_runner_preserves_child_bytes_and_literal_path_arguments(tmp_path: Path, output: bytes) -> None:
    git = tmp_path / "git fixture"
    git.write_text(
        f"#!{sys.executable}\nimport json, sys\nsys.stdout.buffer.write(json.dumps(sys.argv[1:]).encode() + b'\\n')\nsys.stdout.buffer.write({output!r})\n",
        encoding="utf-8",
    )
    git.chmod(0o700)

    result = capture_scope._run_git(str(git), tmp_path, ("probe", "--", "literal [*].py"))

    arguments, child_output = result.split(b"\n", 1)
    assert json.loads(arguments) == ["--literal-pathspecs", "-C", str(tmp_path), "probe", "--", "literal [*].py"]
    assert child_output == output


def test_shared_git_runner_retains_nonzero_exit_and_binary_stderr_context(tmp_path: Path) -> None:
    git = tmp_path / "git fixture"
    git.write_text(f"#!{sys.executable}\nimport sys\nsys.stderr.buffer.write(b'broken\\xff\\n')\nsys.exit(7)\n", encoding="utf-8")
    git.chmod(0o700)

    with pytest.raises(RuntimeError, match=r"git probe failed \(7\): broken�"):
        capture_scope._run_git(str(git), tmp_path, ("probe",))


def test_capture_timeout_reports_both_captured_streams_without_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def timed_out(*_args: Any, **_kwargs: Any) -> bytes:
        raise subprocess.TimeoutExpired(["git", "rev-parse"], 30, output=b"partial\r\n", stderr=b"diagnostic\xff\n")

    monkeypatch.setattr(capture_scope, "_run_git", timed_out)
    monkeypatch.setattr(sys, "argv", ["capture_scope.py", "--repo", str(tmp_path)])

    assert capture_scope.main() == 2

    result = capsys.readouterr()
    assert result.out == ""
    assert "timed out after 30 seconds" in result.err
    assert "stdout:\npartial" in result.err
    assert "stderr:\ndiagnostic�" in result.err
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("failed_query", ["check-ignore", "ls-files"])
def test_ignored_artifact_verification_propagates_fatal_git_queries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_query: str) -> None:
    prior = tmp_path / "prior.json"
    prior.write_bytes(b'{"status":"valid"}\n')

    def run(command: str, args: tuple[str, ...], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if failed_query in args:
            return subprocess.CompletedProcess([command, *args], 128, b"", b"fatal: fixture object database is unreadable\n")
        return subprocess.CompletedProcess([command, *args], 0, b".gitignore\x001\x00cache/\x00cache/output\x00", b"")

    monkeypatch.setattr(plan, "run_command_bytes", run)

    with pytest.raises(subprocess.CalledProcessError) as failure:
        plan._verified_artifact_status("cache/output", "ignored", tmp_path.resolve())

    assert failure.value.returncode == 128
    assert failed_query in failure.value.cmd
    assert failure.value.stderr == b"fatal: fixture object database is unreadable\n"
    assert prior.read_bytes() == b'{"status":"valid"}\n'
    assert list(tmp_path.iterdir()) == [prior]


def test_workspace_classification_propagates_fatal_git_queries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    failed = subprocess.CompletedProcess(["git", "ls-files"], 128, b"", b"fatal: fixture object database is unreadable\n")
    monkeypatch.setattr(runtime, "run_command_bytes", lambda *_args, **_kwargs: failed)
    monkeypatch.setattr(plan, "run_command_bytes", lambda *_args, **_kwargs: failed)
    root = tmp_path.resolve()

    with pytest.raises(subprocess.CalledProcessError) as failure:
        runtime._git_path_status(root, root / "cache/output")

    assert failure.value.returncode == 128
    assert failure.value.stderr == b"fatal: fixture object database is unreadable\n"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("output", "message"),
    [
        (b"", "not ignored by repository policy"),
        (b"not-ignore-provenance\n", "could not parse Git ignore provenance"),
        (b".gitignore\x000\x00cache/\x00cache/output\x00", "could not parse Git ignore provenance"),
        (b".gitignore\x001\x00cache/\x00other/output\x00", "could not parse Git ignore provenance"),
        (b".gitignore\x001\x00cache/\x00cache/output", "could not parse Git ignore provenance"),
    ],
)
def test_ignored_artifact_verification_rejects_empty_and_malformed_git_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output: bytes, message: str
) -> None:
    response = subprocess.CompletedProcess(["git", "check-ignore"], 0, output, b"")
    monkeypatch.setattr(plan, "run_command_bytes", lambda *_args, **_kwargs: response)

    with pytest.raises(ValueError, match=message):
        plan._verified_artifact_status("cache/output", "ignored", tmp_path.resolve())
    assert not list(tmp_path.iterdir())


def test_workspace_classification_retains_valid_git_nonmatches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nonmatch = subprocess.CompletedProcess(["git", "fixture"], 1, b"", b"")
    monkeypatch.setattr(runtime, "run_command_bytes", lambda *_args, **_kwargs: nonmatch)
    monkeypatch.setattr(plan, "run_command_bytes", lambda *_args, **_kwargs: nonmatch)
    root = tmp_path.resolve()

    assert runtime._git_path_status(root, root / "cache/output") == "untracked"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("directory", ["é", "with\ttab", "with:colon"])
def test_ignored_artifact_verification_preserves_unquoted_nested_rule_paths(tmp_path: Path, directory: str) -> None:
    repository = tmp_path / "repository"
    _init_repo(repository)
    rule = repository / directory / ".gitignore"
    rule.parent.mkdir()
    rule.write_text("generated/\n", encoding="utf-8")
    _git(repository, "add", "--", f"{directory}/.gitignore")
    protected = rule.read_bytes()
    artifact = repository / directory / "generated" / "output.json"

    source, provenance = plan._verified_artifact_status(str(artifact), "ignored", repository.resolve())

    assert source == "repository-rule"
    assert provenance == f"{directory}/.gitignore:1:generated/"
    assert rule.read_bytes() == protected
    assert not artifact.exists()


def test_explicit_unignore_rule_does_not_authorize_validation_output(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    _init_repo(repository)
    rule = repository / ".gitignore"
    rule.write_text("*.log\n!important.log\n", encoding="utf-8")
    _git(repository, "add", ".gitignore")
    protected = rule.read_bytes()

    with pytest.raises(ValueError, match="not ignored by repository policy"):
        plan._verified_artifact_status("important.log", "ignored", repository.resolve())

    assert runtime._git_path_status(repository.resolve(), repository.resolve() / "important.log") == "untracked"
    assert rule.read_bytes() == protected
    assert not (repository / "important.log").exists()


def test_runtime_fatal_git_diagnostic_uses_stderr_and_preserves_prior_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    document, _dispatches = _worker_input_fixture(tmp_path)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(document), encoding="utf-8")
    output_path = tmp_path / "output.json"
    protected = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    def fatal(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.CalledProcessError(128, ["git", "ls-files"], output=b"partial\n", stderr=b"fatal: fixture repository is unreadable\n")

    monkeypatch.setattr(runtime, "_run_operation", fatal)

    assert runtime.main(["materialize-dispatches", "--input", str(input_path), "--output", str(output_path)]) == 2

    result = capsys.readouterr()
    assert result.out == ""
    assert "exit status 128: git ls-files" in result.err
    assert "stdout:\npartial" in result.err
    assert "stderr:\nfatal: fixture repository is unreadable" in result.err
    assert not output_path.exists()
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == protected


def test_bootstrap_fatal_git_diagnostic_uses_stderr_and_preserves_prior_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    capture_path, template_path, output_path = (tmp_path / name for name in ("capture.json", "template.json", "output.json"))
    capture_path.write_text(json.dumps(_baseline_capture()), encoding="utf-8")
    template_path.write_text(json.dumps(_sparse_plan_document()), encoding="utf-8")
    output_path.write_bytes(b'{"status":"prior-valid-output"}\n')
    protected = {path: path.read_bytes() for path in tmp_path.iterdir()}

    def fatal(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.CalledProcessError(128, ["git", "check-ignore"], stderr=b"fatal: fixture repository is unreadable\n")

    monkeypatch.setattr(bootstrap, "plan_from_document", fatal)

    assert bootstrap.main(["--capture", str(capture_path), "--input", str(template_path), "--output", str(output_path)]) == 2

    result = capsys.readouterr()
    assert result.out == ""
    assert "exit status 128: git check-ignore" in result.err
    assert "stderr:\nfatal: fixture repository is unreadable" in result.err
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == protected


def test_generated_capture_and_publication_commands_keep_the_dependency_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
    interpreter = environment / "bin" / "python"
    uv = shutil.which("uv")
    assert uv is not None
    # A locked sync caches wheel URLs without requiring registry metadata for offline resolution.
    installation = subprocess.run(  # noqa: S603 - locked tooling dependencies installed offline into the temporary environment.
        [
            uv,
            "sync",
            "--locked",
            "--offline",
            "--only-group",
            "tooling",
            "--project",
            str(SKILL_ROOT.parents[2]),
            "--python",
            str(interpreter),
            "--no-python-downloads",
        ],
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(environment)},
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert installation.returncode == 0, installation.stderr.decode(errors="replace")
    isolated = subprocess.run(  # noqa: S603 - temporary environment's Python, fixed read-only import inspection.
        [str(interpreter), "-c", "import importlib.util; print(importlib.util.find_spec('pytest'))"], capture_output=True, check=True, timeout=30
    )
    assert isolated.stdout == b"None\n"
    monkeypatch.setattr(sys, "executable", str(interpreter))

    capture = shlex.split(_capture_command({"capture_mode": "baseline", "repository_root": str(tmp_path)}))
    _document, dispatches = _worker_input_fixture(tmp_path)
    persistence = dispatches["dispatches"][0]["dispatch"]["worker_payload_persistence"]
    commands = [capture, *(persistence[key] for key in ("command", "review_command", "publish_command"))]
    protected = {path: path.read_bytes() for path in (tmp_path / "proof").rglob("*") if path.is_file()}

    for command in commands:
        assert command[0] == str(interpreter)
        result = subprocess.run([*command, "--help"], capture_output=True, check=False, timeout=30)  # noqa: S603 - generated read-only help commands.
        assert result.returncode == 0, result.stderr
        assert b"usage:" in result.stdout
        assert result.stderr == b""
    assert {path: path.read_bytes() for path in (tmp_path / "proof").rglob("*") if path.is_file()} == protected
