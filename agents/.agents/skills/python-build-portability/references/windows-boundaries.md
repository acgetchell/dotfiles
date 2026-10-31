# Windows Source And Fixture Boundaries

Apply this review to changed code and fixtures exercised on Windows, including
unpackaged repository tooling. Inspect unchanged CI configuration to identify
the actual shell, Python version, and native tools.

Trace native Python paths through the configured shell. Git Bash/MSYS `$PWD`,
Windows drive/UNC paths, separators, case, quoting, spaces, and non-ASCII names
need not have identical string representations. Compare filesystem identity
when that is the contract; use explicit normalization only for a defined
textual format. A fixture that compares a shell's cwd string to `str(Path)`
needs this review even if production code already handles paths correctly.

`OSError` renders filenames with repr-style quoting and escaping, so Windows
backslashes can be doubled in diagnostics. Distinguish that representation from
application messages that deliberately print raw paths.

`Path.write_text()` can translate LF to CRLF on Windows; Git's
`core.autocrlf=false` does not control Python writes. Identify whether the
contract requires unchanged bytes or text with a specified newline convention.
Route fixture construction and regression assertions to
`python-test-quality/references/platform-regression-evidence.md`.

Treat `readlink()` output as an OS representation, not a round trip of the
argument passed to `symlink_to()`. Windows may return a substitution path with
the `\\?\` prefix. Use `link.samefile(expected_target)` for an existing target's
identity; do not strip prefixes as a general normalization rule. Relative link
targets are relative to the link's parent, not the process cwd.

Review executable lookup (`.exe`, `.cmd`, `PATHEXT`, shebangs), symlink
privileges, open-file replacement/deletion, and encoding/newline behavior where
the changed boundary depends on them. Route durable fixture evidence to
`python-test-quality` and support-process transport to `python-support-scripts`.

## Imports And Platform Targets

Trace both import-time and call-time use of platform-specific standard-library
modules and constants, including helper entry points launched by filename or
with `-I -S`. Guard the implementation's imports and uses, not only its callers.
Where the configured type checker supports Windows targeting, apply it to the
affected source and tests before an expensive native run. A model or successful
POSIX import cannot establish Windows importability.

## Stream And Process Boundaries

Trace producer, spool or pipe, forwarder, caller, and diagnostic output for both
stdout and stderr. Check binary mode at every boundary, short reads/writes,
buffering, shared stream ordering, descriptor/handle inheritance, delete sharing,
and cleanup while descendants retain handles. A binary final consumer cannot
repair bytes changed earlier. Separate Python text/newline translation from
Windows CRT descriptor modes; do not infer a specific transformation from a
generic byte-mismatch assertion.

Filename visibility does not establish immediate readability. On Windows a
rename can make the new name visible before the renamer closes its DELETE
handle; another process's ordinary read open can fail without compatible
`FILE_SHARE_DELETE`. Review `exists()`/notification-then-open handshakes and
completion files as well as output payloads. Prefer a protocol that does not
need a conflicting open, or establish the required sharing explicitly. See
[Microsoft's rename-stage explanation](https://devblogs.microsoft.com/oldnewthing/20211022-00/?p=105822).

Exercise successful output, expected validation failures, child failure, and
timeouts while preserving the same literal CRLF/non-UTF-8 payload and stream
ownership. An expected nonzero status must be caused by the expected failure:
an unrelated forwarder or cleanup error must not satisfy a missing-marker test.
Include callable helpers and their real subprocess fixtures even when the
workflow or helper was not changed in the patch.

## Native Failure Diagnosis

Start with the failed job's actual output and preserve the existing regression
contract. If assertions hide decisive values, obtain bounded diagnostic evidence
before choosing a fix.

For a byte mismatch, inspect bounded evidence such as lengths, the first differing
offset, and small escaped prefix/suffix windows. Keep large payloads and private
output out of logs. Preserve the original payload and assertion; add diagnostic
context instead of normalizing away CRLFs, accepting partial output, or weakening
expected success. For ordering failures, identify which process writes each
stream and how completion is synchronized before changing buffering or timing.

Run the implicated existing regression early on the native platform where
practical, without removing it from the complete source and installed suites.
Follow the required checks for the fixed commit; queued jobs and successful
startup probes do not establish package or platform correctness.

If a local model is used, demonstrate its sensitivity to the
defective boundary and leave native confirmation explicit. A successful retry
does not by itself explain or resolve an intermittent failure. If the log lacks
the decisive values, say that the cause is unproven and collect those values
rather than presenting a guess as a Windows fix.

Inspect native Windows CI evidence supplied by the coordinator; report missing,
stale, or failed evidence as a gap. A passing local run or path model cannot
resolve a native Windows failure. Preserve the failing job/step and require
current native evidence before claiming the Windows fix is verified.
