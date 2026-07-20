# Binary And API Front Ends

Load this reference when notebook cells invoke external commands, wrap a library API as the computational engine, parse subprocess output, or need portable repository-root discovery.

## Keep The Engine Separate

Keep production simulation, transformation, and validation logic in the binary or importable library. Let notebook cells construct inputs, invoke the engine, load artifacts, and explain results.

Avoid duplicating production algorithms in cells. Extract a reusable typed helper when command construction or response parsing becomes non-trivial.

## Commands

Check:

- subprocesses use argument lists rather than interpolated shell strings
- timeouts or explicit runtime expectations prevent silent hangs
- working directory and environment are deliberate
- parsed output uses a stable machine-readable mode
- failures preserve the command, exit code, stdout, and stderr without leaking secrets
- machine-readable stdout remains separate from tutorial or diagnostic text
- binary paths can be supplied through repository configuration or a documented environment variable

Streaming output is acceptable for tutorial front doors when failures still retain enough context for reproduction.

## Paths And Artifacts

Discover the repository root from explicit configuration or stable marker files instead of assuming the launch directory. Validate constructed inputs and outputs before use. Write ordinary runs under a documented disposable root and load artifacts back through a validated parser.

## API Front Ends

For in-process libraries, check that the notebook calls public APIs, manages context managers and resources, avoids relying on private internals, and presents exceptions with useful notebook-level context. Route package installation/import behavior to `python-build-portability` and invariant-bearing response parsing to `python-parse-dont-validate`.
