"""Native process and shell checks for validation timing without third-party packages."""

# ruff: noqa: PT009 -- unittest also runs in the dependency-free Windows CI job.

import io
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, override
from unittest.mock import patch

import run_timed

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TextIO

RUNNER = Path(run_timed.__file__).resolve()
PROBE = """import json, os, sys, time
time.sleep(0.1)
print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'env': os.environ.get('TIMING_TEST_VALUE')}))
os.write(2, b'child stderr\\n')
sys.exit(23)
"""


class TestTimingRunner(unittest.TestCase):
    """Check timing records against real subprocess behavior."""

    @override
    def setUp(self) -> None:
        """Keep launch inputs and artifacts outside the repository."""
        self.temporary = tempfile.TemporaryDirectory(prefix="validation timing ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "launch input.json"
        self.receipt = self.root / "timing receipt.jsonl"

    def launch(self, code: str = "pass", *arguments: str) -> list[str]:
        """Write an exact native Python command, including unusual arguments."""
        self.source.write_text(
            json.dumps({"schema_version": 1, "argv": [sys.executable, "-c", code, *arguments], "working_directory": str(self.root)}), encoding="utf-8"
        )
        return [sys.executable, str(RUNNER), "--input", str(self.source), "--receipt", str(self.receipt)]

    def events(self) -> list[dict[str, object]]:
        """Read only complete lines from the bounded per-command receipt."""
        return [json.loads(line) for line in self.receipt.read_text(encoding="utf-8").splitlines()]

    def run_cli(self, argv: list[str] | str) -> subprocess.CompletedProcess[str]:
        """Bound test processes while retaining independent stdout and stderr."""
        return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=15)  # noqa: S603 -- fixture-owned arguments

    def test_success_has_execution_side_timing(self) -> None:
        outcome = self.run_cli(self.launch("import time; time.sleep(0.1)"))
        self.assertEqual(outcome.returncode, 0)
        self.assertEqual(outcome.stdout, "")
        start, finish = self.events()
        self.assertEqual(start["event"], "attempt-started")
        self.assertEqual(finish["status"], "completed")
        self.assertEqual(finish["exit_code"], 0)
        assert finish["command_started"] is True
        elapsed = finish["elapsed_seconds"]
        assert isinstance(elapsed, float)
        self.assertGreaterEqual(elapsed, 0.1)

    def test_nonzero_exit_preserves_arguments_directory_environment_and_streams(self) -> None:
        arguments = ("", "two words", "quotes\"'", "$HOME; & | %PATH%", "café", "trailing\\")
        argv = self.launch(PROBE, *arguments)
        with patch.dict(os.environ, {"TIMING_TEST_VALUE": "inherited fixture value"}):
            outcome = self.run_cli(argv)
        self.assertEqual(outcome.returncode, 23)
        self.assertEqual(json.loads(outcome.stdout), {"argv": list(arguments), "cwd": str(self.root), "env": "inherited fixture value"})
        self.assertEqual(outcome.stderr, "child stderr\n")
        self.assertEqual(self.events()[1]["exit_code"], 23)
        self.assertNotIn("inherited fixture value", self.receipt.read_text(encoding="utf-8"))

    def test_launch_failure_is_not_an_executed_command_failure(self) -> None:
        argv = self.launch()
        value = json.loads(self.source.read_text(encoding="utf-8"))
        value["argv"] = [str(self.root / "nonexistent-executable")]
        self.source.write_text(json.dumps(value), encoding="utf-8")
        outcome = self.run_cli(argv)
        self.assertEqual(outcome.returncode, 2)
        finish = self.events()[1]
        self.assertEqual(finish["status"], "launch-failed")
        assert finish["command_started"] is False
        self.assertIsNone(finish["exit_code"])
        self.assertEqual(finish["error_type"], "FileNotFoundError")

    def test_command_exit_two_is_still_an_executed_failure(self) -> None:
        outcome = self.run_cli(self.launch("raise SystemExit(2)"))
        self.assertEqual(outcome.returncode, 2)
        self.assertEqual(self.events()[1]["status"], "completed")
        assert self.events()[1]["command_started"] is True
        self.assertEqual(self.events()[1]["exit_code"], 2)

    def test_preflight_rejects_invalid_specs_and_unsupported_wrappers(self) -> None:
        argv = self.launch("from pathlib import Path; Path('child-started').touch()")
        valid = json.loads(self.source.read_text(encoding="utf-8"))
        invalid = [
            {**valid, "timing_wrapper": "time -p"},
            {**valid, "environment": {}},
            {**valid, "schema_version": True},
            {**valid, "argv": "just ci"},
            {**valid, "argv": []},
            {**valid, "argv": [""]},
            {**valid, "argv": ["bad\0program"]},
            {**valid, "working_directory": "."},
            {**valid, "working_directory": str(self.root / "missing")},
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.source.write_text(json.dumps(value), encoding="utf-8")
                self.assertEqual(self.run_cli(argv).returncode, 2)
                self.assertFalse((self.root / "child-started").exists())
                self.assertFalse(self.receipt.exists())
        self.source.write_text(json.dumps(valid).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'), encoding="utf-8")
        self.assertEqual(self.run_cli(argv).returncode, 2)
        self.assertFalse(self.receipt.exists())

    def test_receipt_failure_prevents_execution_and_preserves_old_evidence(self) -> None:
        argv = self.launch("from pathlib import Path; Path('child-started').touch()")
        self.receipt.write_text("prior evidence\n", encoding="utf-8")
        self.assertEqual(self.run_cli(argv).returncode, 74)
        self.assertEqual(self.receipt.read_text(encoding="utf-8"), "prior evidence\n")
        self.assertFalse((self.root / "child-started").exists())
        argv[-1] = str(self.root / "absent" / "receipt.jsonl")
        self.assertEqual(self.run_cli(argv).returncode, 74)
        self.assertFalse((self.root / "child-started").exists())

    def test_monotonic_clock_not_wall_clock_supplies_duration(self) -> None:
        self.launch()
        with (
            patch.object(run_timed.time, "monotonic_ns", side_effect=[100_000_000_000, 102_500_000_000]),
            patch.object(run_timed.time, "time", side_effect=AssertionError("Wall-clock time must not supply duration")),
        ):
            self.assertEqual(run_timed.main(["--input", str(self.source), "--receipt", str(self.receipt)]), 0)
        self.assertEqual(self.events()[1]["elapsed_seconds"], 2.5)

    def test_stdin_and_binary_output_are_not_reencoded(self) -> None:
        argv = self.launch("import os; os.write(1, os.read(0, 4) + b'\\x00\\xff\\r\\n')")
        outcome = subprocess.run(argv, input=b"data", capture_output=True, check=False, timeout=10)  # noqa: S603 -- fixture-owned arguments
        self.assertEqual(outcome.returncode, 0)
        self.assertEqual(outcome.stdout, b"data\x00\xff\r\n")
        self.assertEqual(outcome.stderr, b"")

    def test_late_receipt_failure_does_not_reclassify_or_repeat_execution(self) -> None:
        self.launch("from pathlib import Path; Path('child-started').write_text('once')")
        record = run_timed._record

        def fail_final_record(stream: TextIO, event: dict[str, object]) -> None:
            if event["event"] == "finished":
                message = "fixture exception text"
                raise OSError(message)
            record(stream, event)

        stderr = io.StringIO()
        with patch.object(run_timed, "_record", side_effect=fail_final_record), patch.object(sys, "stderr", stderr):
            self.assertEqual(run_timed.main(["--input", str(self.source), "--receipt", str(self.receipt)]), 74)
        self.assertEqual((self.root / "child-started").read_text(), "once")
        self.assertEqual(len(self.events()), 1)
        self.assertNotIn("fixture exception text", stderr.getvalue())

    def test_async_polling_does_not_finish_or_retime_the_command(self) -> None:
        code = """from pathlib import Path
import time
Path('ready').touch()
while not Path('release').exists():
    time.sleep(0.01)
"""
        with subprocess.Popen(self.launch(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:  # noqa: S603 -- fixture-owned arguments
            try:
                self.wait_for(self.root / "ready")
                self.assertIsNone(process.poll())
                self.assertEqual(len(self.events()), 1)
                (self.root / "release").touch()
                process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0)
                recorded = self.receipt.read_bytes()
                # Observing the already-finished session never changes its evidence.
                process.poll()
                process.wait()
                self.assertEqual(self.receipt.read_bytes(), recorded)
                self.assertEqual(self.events()[1]["status"], "completed")
            finally:
                (self.root / "release").touch()
                process.wait(timeout=5)

    def wait_for(self, path: Path) -> None:
        """Wait for a subprocess handshake rather than assuming scheduling speed."""
        deadline = time.monotonic() + 5
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(path.exists(), "child did not reach the handshake")

    @unittest.skipIf(os.name == "nt", "POSIX signal return codes")
    def test_signal_exit_retains_raw_code(self) -> None:
        outcome = self.run_cli(self.launch("import os, signal; os.kill(os.getpid(), signal.SIGTERM)"))
        self.assertEqual(outcome.returncode, 128 + signal.SIGTERM)
        self.assertEqual(self.events()[1]["exit_code"], -signal.SIGTERM)
        self.assertEqual(self.events()[1]["status"], "completed")

    @unittest.skipIf(os.name == "nt", "POSIX runner-only interrupt delivery")
    def test_interruption_is_not_success_or_not_run(self) -> None:
        argv = self.launch("from pathlib import Path; import time; Path('ready').touch(); time.sleep(30)")
        with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:  # noqa: S603 -- fixture-owned arguments
            try:
                self.wait_for(self.root / "ready")
                process.send_signal(signal.SIGINT)
                process.communicate(timeout=10)
                self.assertEqual(process.returncode, 130)
                finish = self.events()[1]
                self.assertEqual(finish["status"], "interrupted")
                assert finish["command_started"] is True
                self.assertNotEqual(finish["exit_code"], 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    @unittest.skipIf(os.name == "nt", "native bash and zsh execution")
    def test_posix_executor_shells(self) -> None:
        for name in ("bash", "zsh"):
            with self.subTest(shell=name):
                executable = shutil.which(name)
                if executable is None:
                    self.skipTest(f"native {name} unavailable")
                self.check_shell(executable, ["-c"], shlex.join)

    @unittest.skipUnless(os.name == "nt", "native Windows executor shells; exercised by CI")
    def test_windows_executor_shells(self) -> None:
        for name in ("cmd", "powershell", "pwsh"):
            with self.subTest(shell=name):
                executable = shutil.which(name)
                if executable is None:
                    self.fail(f"required native executor {name} unavailable")
                if name == "cmd":
                    self.check_shell(executable, ["/d", "/s", "/c"], subprocess.list2cmdline)
                else:
                    self.check_shell(executable, ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command"], powershell_command)

    def check_shell(self, executable: str, flags: list[str], quote: Callable[[list[str]], str]) -> None:
        """Execute the wrapper through a real shell while its child uses exact argv."""
        self.receipt.unlink(missing_ok=True)
        argv = self.launch(PROBE, "", "literal $;&|%", "two words")
        # cmd consumes a raw command line; do not C-runtime-escape it a second time.
        invocation = f'"{executable}" /d /s /c "{quote(argv)}"' if flags[0] == "/d" else [executable, *flags, quote(argv)]
        outcome = self.run_cli(invocation)
        self.assertEqual(outcome.returncode, 23, outcome.stderr)
        self.assertEqual(json.loads(outcome.stdout)["argv"], ["", "literal $;&|%", "two words"])
        self.assertEqual(json.loads(outcome.stdout)["cwd"], str(self.root))
        self.assertEqual(outcome.stderr, "child stderr\n")
        self.assertEqual(self.events()[1]["exit_code"], 23)
        elapsed = self.events()[1]["elapsed_seconds"]
        assert isinstance(elapsed, float)
        self.assertGreaterEqual(elapsed, 0.1)


def powershell_command(argv: list[str]) -> str:
    """Retain the native helper's exit status through the PowerShell test transport."""
    return "& " + " ".join("'" + argument.replace("'", "''") + "'" for argument in argv) + "; exit $LASTEXITCODE"


if __name__ == "__main__":
    unittest.main()
