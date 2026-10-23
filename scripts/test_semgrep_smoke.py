"""Require Windows CI to exercise the native scanner engine."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

import semgrep_smoke

REPOSITORY = Path(__file__).resolve().parents[1]


def test_windows_ci_runs_the_native_engine_smoke() -> None:
    workflow = yaml.safe_load((REPOSITORY / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["validation-timing"]["steps"]
    windows_commands = [step.get("run", "") for step in steps if step.get("if") == "runner.os == 'Windows'"]
    assert any("uv run --locked --project tooling/semgrep python scripts/semgrep_smoke.py" in command for command in windows_commands)


def test_real_native_scanner_engine_finds_the_fixture() -> None:
    environment = Path(os.environ.get("DOTFILES_SEMGREP_ENVIRONMENT", REPOSITORY / "tooling/semgrep/.venv"))
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    result = subprocess.run(  # noqa: S603 - actual locked scanner environment, fixed offline fixture.
        [str(python), str(REPOSITORY / "scripts/semgrep_smoke.py")], check=False, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "one expected finding, no errors" in result.stdout


@pytest.mark.parametrize(
    "report",
    [
        {},
        [],
        {"errors": [], "results": []},
        {"errors": [], "results": [None]},
        {"errors": [{"message": "engine failure"}], "results": [{"check_id": semgrep_smoke.RULE_ID, "path": "fixture.py"}]},
        {"errors": [], "results": [{"check_id": "wrong-rule", "path": "fixture.py"}]},
        {"errors": [], "results": [{"check_id": semgrep_smoke.RULE_ID, "path": "wrong.py"}]},
        {"errors": [], "results": [{"check_id": semgrep_smoke.RULE_ID, "path": "fixture.py"}] * 2},
    ],
)
def test_native_smoke_rejects_missing_findings_and_core_errors(report: object) -> None:
    with pytest.raises(ValueError, match="Semgrep native engine"):
        semgrep_smoke.validate_scan(subprocess.CompletedProcess(["semgrep"], 0, json.dumps(report), ""))


@pytest.mark.parametrize(("code", "output"), [(7, '{"errors":[],"results":[]}'), (0, "not JSON")])
def test_native_smoke_rejects_process_and_output_failures(code: int, output: str) -> None:
    with pytest.raises(ValueError, match="Semgrep native engine"):
        semgrep_smoke.validate_scan(subprocess.CompletedProcess(["semgrep"], code, output, ""))


def _selected_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(semgrep_smoke.sys, "executable", str(tmp_path / "python"))
    launcher = tmp_path / ("semgrep.exe" if os.name == "nt" else "semgrep")
    launcher.write_text("", encoding="utf-8")
    return launcher


def test_missing_scanner_launcher_reports_the_required_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(semgrep_smoke.sys, "executable", str(tmp_path / "python"))
    assert semgrep_smoke.main() == 2
    output = capsys.readouterr()
    assert "uv run --locked --project tooling/semgrep python" in output.err
    assert output.out == ""


@pytest.mark.parametrize(
    ("failure", "diagnostic"), [(PermissionError("scanner launch denied"), "scanner launch denied"), (subprocess.TimeoutExpired(["semgrep"], 90), "timed out")]
)
def test_scanner_launch_failures_report_stderr_and_exit_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], failure: OSError | subprocess.TimeoutExpired, diagnostic: str
) -> None:
    launcher = _selected_launcher(tmp_path, monkeypatch)

    def fail_launch(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert argv[0] == str(launcher)
        raise failure

    monkeypatch.setattr(semgrep_smoke.subprocess, "run", fail_launch)
    assert semgrep_smoke.main() == 2
    output = capsys.readouterr()
    assert "Native Semgrep smoke failed:" in output.err
    assert diagnostic in output.err
    assert output.out == ""


@pytest.mark.parametrize(("outcome", "diagnostic"), [((7, "{}"), "exited with status 7"), ((0, "not JSON"), "did not emit a JSON result")])
def test_scanner_result_failures_preserve_core_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], outcome: tuple[int, str], diagnostic: str
) -> None:
    launcher = _selected_launcher(tmp_path, monkeypatch)
    result = subprocess.CompletedProcess([str(launcher)], *outcome, "native core diagnostic\n")
    monkeypatch.setattr(semgrep_smoke.subprocess, "run", lambda *_args, **_kwargs: result)
    assert semgrep_smoke.main() == 2
    output = capsys.readouterr()
    assert "native core diagnostic" in output.err
    assert diagnostic in output.err
    assert output.out == ""
