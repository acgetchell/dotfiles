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

Treat `readlink()` output as an OS representation, not a round trip of the
argument passed to `symlink_to()`. Windows may return a substitution path with
the `\\?\` prefix. Use `link.samefile(expected_target)` for an existing target's
identity; do not strip prefixes as a general normalization rule. Relative link
targets are relative to the link's parent, not the process cwd.

Review executable lookup (`.exe`, `.cmd`, `PATHEXT`, shebangs), symlink
privileges, open-file replacement/deletion, and encoding/newline behavior where
the changed boundary depends on them. Route durable fixture evidence to
`python-test-quality` and support-process transport to `python-support-scripts`.

Inspect native Windows CI evidence supplied by the coordinator; report missing,
stale, or failed evidence as a gap. A passing local run or path model cannot
resolve a native Windows failure. Preserve the failing job/step and require
current native evidence before claiming the Windows fix is verified.
