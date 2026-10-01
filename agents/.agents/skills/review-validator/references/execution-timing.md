# Timing Asynchronous Validation Commands

Use [`scripts/run_timed.py`](../scripts/run_timed.py) under the approved Python
runtime. It measures monotonic time from subprocess creation through exit,
independently of the executor shell and polling. Do not construct a shell
`time -p` wrapper: that syntax does not work consistently across executor shells.

## Prepare The Launch

Before dispatch, the coordinator supplies a launch JSON file and a new timing
receipt path as approved ignored/external artifacts. For example, when the
authorized command is `just ci`:

```json
{
  "schema_version": 1,
  "argv": ["just", "ci"],
  "working_directory": "/absolute/dispatched/working-directory"
}
```

Use the exact executable and arguments from the dispatch. Do not split a shell
command with whitespace or translate it into a different shell. A command that
requires shell syntax must name the declared shell and its exact invocation
arguments in `argv`. Preserve its existing profile, quoting, and exit-status
policy; the receipt records that process's exit code. Batch files and shell
builtins require an explicit, authorized shell invocation. The helper never
adds a shell, changes shell flags, or retries using a fallback wrapper.

Run the helper in the dispatched environment using the same approved Python
launcher as the other graph helpers. For a repository whose launcher is
`uv run --locked python`, invoke:

```sh
uv run --locked python <review-validator-dir>/scripts/run_timed.py \
  --input <approved-launch.json> --receipt <new-absolute-receipt.jsonl>
```

The helper validates the launch shape and directory and reserves the receipt
before starting a child. Unknown fields, including alternate timing-wrapper
options, are rejected before execution. It does not modify the argument vector,
working directory, inherited environment, or stdin/stdout/stderr. Environment
values are not serialized. Keep secrets out of command arguments. Launch JSON
uses host-native absolute paths, including on Windows; timing does not depend
on bash, zsh, PowerShell, Windows PowerShell, or cmd syntax.

## Interpret The Receipt

The private JSONL receipt starts with `attempt-started` and ends with a
`finished` record. These records are timing evidence, not graph acceptance or a
replacement for source-state verification. Match the recorded command and
directory to the dispatch and retain its source/environment bindings.

| Final status | Interpretation |
| --- | --- |
| `completed`, exit `0` | Command passed; use `elapsed_seconds`. |
| `completed`, nonzero exit | Command ran and failed; retain its exit code and elapsed time. |
| `launch-failed`, `command_started: false` | No command executed; report the launch blocker and leave `executions` empty if no other command ran. |
| `interrupted` | Child started but execution was interrupted; retain its exit code and timing, and report blocked evidence. |
| Missing, partial, or no `finished` record | Complete timing evidence is unavailable; do not infer success or rerun automatically. |

The helper returns the child process's exit status for completed commands.
On POSIX, signal termination retains the negative subprocess code in the receipt
and returns `128 + signal` to the shell. Exit `2` can mean launch failure or an
actual command exiting `2`; the receipt distinguishes them. Exit `74` indicates
a receipt I/O failure and `130` an interrupted helper; inspect the receipt
rather than classifying execution from the helper's exit code alone. A receipt
failure after execution must not be treated as an unstarted command.

An interrupt observed by the helper terminates and waits for its direct child.
Session cancellation and descendant process cleanup remain the executor's
responsibility. Abrupt termination may leave only the initial record.

## Polling And Recovery

When execution yields a session ID, poll that same session through completion
and retrieve its final exit status and timing record. Polling wait durations,
the first tool call's duration, and the delay before observing completion are
not the command's full elapsed time. For an already completed command, recover
the execution-side timing from the existing session output or log; do not rerun
the check to fill in the payload. If no complete timing was captured and none
can be recovered, report the missing evidence and leave publication blocked.
Do not invent a duration or relabel a completed command as `not-run`.

## Accepted Elapsed Values

Numeric elapsed values represent finite, nonnegative seconds. Duration strings
use an unsigned decimal number (optionally scientific notation) and an optional
`ms`, `s`, `m`, or `h` suffix; no suffix means seconds. Examples include `"3.2s"`,
`"250ms"`, and `"1.5m"`. Arbitrary text, negative durations, NaN, infinity, and
values that overflow when converted to seconds are invalid. Passed and failed
executions cannot use null, `"none"`, or blank elapsed data. Blocked executions
may omit timing with null or `"none"`; any supplied duration must still be valid.
Preflight, persistence, and the compiler enforce the same result-dependent rules.
