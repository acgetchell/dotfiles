# Timing Asynchronous Validation Commands

Start timing inside the process that executes the command, before launch, and
record the duration when that command exits. For example, use the declared
shell's `time -p` around the exact dispatched command, or a runner that records
monotonic start and end times around its subprocess wait. Preserve the command's
exit status and output, and retain the timing record in tool output or a
dispatched log artifact. The timing wrapper must not change the dispatched
command, working directory, or environment.

When execution yields a session ID, poll that same session through completion
and retrieve its final exit status and timing record. Polling wait durations,
the first tool call's duration, and the delay before observing completion are
not the command's full elapsed time. For an already completed command, recover
the execution-side timing from the existing session output or log; do not rerun
the check to fill in the payload. If no complete timing was captured and none
can be recovered, report the missing evidence and leave publication blocked.
Do not invent a duration or relabel a completed command as `not-run`.

Numeric elapsed values represent finite, nonnegative seconds. Duration strings
use an unsigned decimal number (optionally scientific notation) and an optional
`ms`, `s`, `m`, or `h` suffix; no suffix means seconds. Examples include `"3.2s"`,
`"250ms"`, and `"1.5m"`. Arbitrary text, negative durations, NaN, infinity, and
values that overflow when converted to seconds are invalid. Passed and failed
executions cannot use null, `"none"`, or blank elapsed data. Blocked executions
may omit timing with null or `"none"`; any supplied duration must still be valid.
Preflight, persistence, and the compiler enforce the same result-dependent rules.
