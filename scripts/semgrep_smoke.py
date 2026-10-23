"""Exercise the selected scanner's native engine with an offline local fixture."""

__lazy_modules__ = ("subprocess", "tempfile")

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RULE_ID = "dotfiles-native-engine-smoke"


def validate_scan(result: subprocess.CompletedProcess[str]) -> None:
    """Require a real expected finding and reject scanner/core failures."""
    if result.returncode:
        msg = f"Semgrep native engine exited with status {result.returncode}."
        raise ValueError(msg)
    try:
        report = json.loads(result.stdout)
    except ValueError as error:
        msg = "Semgrep native engine did not emit a JSON result."
        raise ValueError(msg) from error
    if not isinstance(report, dict) or report.get("errors") != []:
        msg = "Semgrep native engine reported errors or an incomplete result."
        raise ValueError(msg)
    findings = report.get("results")
    if not isinstance(findings, list) or len(findings) != 1 or not isinstance(findings[0], dict):
        msg = "Semgrep native engine did not produce the one expected finding."
        raise ValueError(msg)
    finding = findings[0]
    if finding.get("check_id") != RULE_ID or finding.get("path") != "fixture.py":
        msg = "Semgrep native engine returned an unexpected rule or source path."
        raise ValueError(msg)


def main() -> int:
    """Use the current scanner interpreter's entrypoint, including Windows .exe."""
    executable = Path(sys.executable).parent / ("semgrep.exe" if os.name == "nt" else "semgrep")
    if not executable.is_file():
        print("Run this smoke with uv run --locked --project tooling/semgrep python.", file=sys.stderr)
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix="dotfiles-semgrep-smoke-") as directory:
            root = Path(directory)
            (root / "fixture.py").write_text("print('native scanner fixture')\n", encoding="utf-8")
            config = {"rules": [{"id": RULE_ID, "languages": ["python"], "pattern": "print($VALUE)", "message": "Native scanner fixture", "severity": "INFO"}]}
            (root / "rule.json").write_text(json.dumps(config), encoding="utf-8")
            environment = {
                **os.environ,
                "SEMGREP_SEND_METRICS": "off",
                "OTEL_SDK_DISABLED": "true",
                "SEMGREP_SETTINGS_FILE": str(root / "settings.yml"),
                "SEMGREP_VERSION_CACHE_PATH": str(root / "version-cache"),
                "SEMGREP_LOG_FILE": str(root / "semgrep.log"),
            }
            result = subprocess.run(  # noqa: S603 - selected environment's scanner, fixed local rule and fixture.
                [
                    str(executable),
                    "scan",
                    "--disable-version-check",
                    "--metrics",
                    "off",
                    "--json",
                    "--quiet",
                    "--strict",
                    "--no-rewrite-rule-ids",
                    "--no-git-ignore",
                    "--config",
                    "rule.json",
                    "fixture.py",
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=90,
            )
            try:
                validate_scan(result)
            except ValueError:
                print(result.stderr, file=sys.stderr, end="")
                raise
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        print(f"Native Semgrep smoke failed: {error}", file=sys.stderr)
        return 2
    print("Native Semgrep engine smoke passed: one expected finding, no errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
