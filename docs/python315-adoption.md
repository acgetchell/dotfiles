# Python 3.15 adoption

Dotfiles adopts the published `research-repo-tools==0.1.9` package for
[issue #169](https://github.com/acgetchell/dotfiles/issues/169). Its inherited
Python floor and development selector are both 3.15. No sibling checkout is
required. The upstream package owns consolidated Python validation and file
selection; dotfiles retains its fixtures, skill validation, and graph protocols.

## Language and tooling changes

Explicit lazy imports defer repository selection for single-skill validation,
Git/schema validation for readers of fixed review labels, and CLI/accounting
dependencies until used. Capture-scope and environment-inventory readers also
defer operational imports, including Git subprocess and schema helpers. Fresh
process tests verify the deferred module trees and working CLI help. Imports
with required module initialization remain
eager. The YAML merge-key marker uses the new `sentinel` builtin. Fixed review
labels use `frozendict`, preserving insertion order and JSON encoding while
preventing mutation. These are supported
[Python 3.15 features](https://docs.python.org/3.15/whatsnew/3.15.html).

The lazy imports use Python 3.15's module-local `__lazy_modules__` declaration.
Semgrep 1.180.0 cannot parse the new `lazy` keyword yet; this declaration enables
the same deferred imports while preserving the strict scan and its full scope.

`just python-check` now delegates to shared `python check`: format, lint, and
strict type checking over one complete inventory, including fixtures. It stops
at the first failed batch. The narrower `python-fix` scope remains appropriate
for deliberate negative Semgrep fixtures.

Skill validation selects `CSafeLoader` when available and falls back to
`SafeLoader`. Duplicate-key detection still inspects the composed tree before
construction; aliases, merge overrides, malformed keys, unsafe tags, and CLI
failures are covered against both implementations. No unsafe loader is enabled.

Unpacking comprehensions express set unions directly when assembling inherited
review metadata and coalesced audit ownership. Sorting and deduplication remain
unchanged. Semgrep's pinned parser accepts these comprehensions. Their benefit
here is simpler code; the whole-planner measurement below is effectively neutral.

Closed `TypedDict`s describe schema diagnostics and allowlisted environment,
source, interpreter, and probe metadata. `ToolIdentities` uses typed extra items
for dynamic tool names. These declarations strengthen consumer checks without
changing JSON fields or providing runtime validation. Real ty consumer probes
verify accepted shapes, forbidden extra fields, and incorrectly typed tool
values. Existing diagnostic assertions now use their precise types directly.

Python 3.15 also supplies the statistical sampling profiler through
`just python-profile`. For example, write an artifact outside the checkout:

```sh
just python-profile run --help
just python-profile run -o /tmp/skill-validation.pstats scripts/skill_validate.py --repository .
just python-profile-tracing -o /tmp/skill-validation-tracing.pstats scripts/skill_validate.py --repository .
```

Sampling requires the host's process-memory inspection permissions. This Mac
rejects sampling even outside the execution sandbox; its CLI is available,
but a sampling profile was not produced. The tracing command provides a
working alternative without changing system permissions.

The interpreter's JIT remains opt-in. A prepared build can be exercised with
`PYTHON_JIT=1 just check-skills`; availability and default enablement depend on
the interpreter distribution. No global lazy-import or JIT setting is imposed.

`just python315-benchmark` compares JIT off/on in seven alternating isolated
processes per mode, using the canonical graph fixture at scale 20 (265 paths).
It measures planning, first replay, warmed replay, and whole-process costs,
retains raw samples outside the checkout, verifies source stability and all
four seeded findings, and rejects a build that cannot honor the requested JIT
mode. Planner setup is outside operation timing. Initial control-file creation
remains part of the normal planner operation. The four canonical replays exercise
materialization, publication, retry, and compilation; they do not measure live
validators or model review. Run `just python315-benchmark 9 40` for more repeats
and a larger fixture. This is an optional performance command, separate from CI.

Report schema 2 records the actual mode order for every pair and summarizes
within-pair `on - off` seconds and `on / off` ratios alongside the marginal
timings. Each worker records its executable, Python implementation/build/compiler,
platform, CPU count, dependency versions, and PID from an explicit allowlist.
It retains stdout/stderr in private trial directories, including failed or
timed-out workers. Both parent and worker reject fixture/artifact destinations
inside the resolved checkout, including symlink aliases, before preparing files.

## Paired measurements

The October 14, 2026 measurements used macOS arm64 and the same uv-managed
CPython 3.15.0 executable for every variant, with pytest 9.1.1, Ruff 0.17.0,
ty 0.0.86, and PyYAML 6.0.3. The fixture contained 67 skills and 105 Python
files. The old shared-package environment differed only in its 0.1.8 package
version; optional C-loader builds were isolated from the default environment.

Each row has nine alternating paired trials after an excluded warmup, with
warm bytecode/filesystem caches and sequential processes. Times are median
milliseconds with median absolute deviation (MAD). No concurrent CI run was
included. Installation, package resolution, and network time are excluded.

| Workload | Before, ms (MAD) | After, ms (MAD) | Interpretation |
| --- | ---: | ---: | --- |
| Single-skill CLI, default loader | 54.18 (0.99) | 26.33 (0.53) | About 51% lower startup time with deferred shared imports |
| Repository skill CLI, default loader | 104.82 (1.31) | 105.36 (0.94) | No material change; this path needs selection |
| Fixed review-label import | 20.43 (0.21) | 17.74 (0.15) | About 13% lower startup time |
| Complete Python gate | 716.85 (8.11) | 398.21 (3.00) | About 44% lower time with the published consolidated gate |
| In-process skill validation, optional C loader | 20.18 (0.10) | 5.69 (0.06) | About 72% lower parsing time; requires the optional extension |
| In-process skill validation, JIT off/on | 20.30 (0.16) | 18.75 (0.06) | Narrow local result, about 8%; no general workflow claim |

The old Python gate replayed the previous three shared `files run` commands
over the same source/configuration, omitting its former extra baseline-check
process. This conservatively understates the savings. Single-skill and loader
comparisons used the captured pre-change validator with the installed v0.1.9
dependency. Worker validation excludes imports and Git selection and reports
ten internal samples per subprocess. The C-loader and JIT rows aggregate those
per-process medians and describe optional capabilities, not default speedups.

Raw reports retain source-file hashes, baseline hashes, interpreter/build and
package identities, commands, raw samples, and dispersion. They are produced
outside the checkout. The independent-review renderer was also replayed with
the same dispatch/payload against the captured old implementation: all 7,423
output bytes matched. Existing graph integrity/publication tests remain the
regression authority for frozen artifact identities.

The historical evidence bundles are named `issue-169-adoption` (initial
`report.json`, measured harness, and before copies) and `issue-169-follow-up`
(`comparison.json`, `threading.json`, JIT report, harnesses, and captured before
files). Their local README files give portable preparation and replay commands.
They are retained outside the checkout and are not part of the public repository.
Exact historical replay requires those bundles: the before snapshots include
uncommitted work and cannot be reconstructed from `origin/main` alone. The
tracked `python315-benchmark` recipe reproduces the current JIT workload; it
does not regenerate the historical startup or free-threading tables.

The earlier Python 3.14/3.15 evaluation found little interpreter-only startup
benefit on this workload. Its concurrent full-suite timings established
compatibility and were not used as performance comparisons. These new results
attribute gains to specific implementation changes and keep optional build
features separate.

## Follow-up measurements and policies

The subsequent implementation comparisons used the updated locked environment
(uv 0.13.1, ty 0.0.87) and the same managed CPython 3.15.0. Before copies captured
the existing worktree, including prior graph changes. Startup measurements
have nine alternating pairs after one excluded paired warmup. Planner comparisons
have seven subprocess pairs and twenty internal samples after one excluded
warmup. The JIT benchmark uses the same seven-pair protocol; full replays verify
finding preservation. Measurements ran sequentially without concurrent CI.

| Workload | Before or JIT off, ms (MAD) | After or JIT on, ms (MAD) | Interpretation |
| --- | ---: | ---: | --- |
| Capture-scope import | 44.76 (0.50) | 21.00 (0.60) | About 53% lower startup time |
| Environment-inventory import | 23.53 (0.32) | 18.95 (0.21) | About 19% lower startup time |
| Full planner, unpacking changes | 5.96 (0.07) | 5.93 (0.04) | No material change |
| Warm planner, JIT off/on | 6.08 (0.12) | 5.74 (0.13) | About 5.5% lower time, roughly 0.34 ms |
| First canonical replay, JIT off/on | 507.31 (94.03) | 586.02 (155.03) | Mixed, with substantial filesystem variation |
| Warm canonical replay, JIT off/on | 372.77 (6.67) | 369.72 (7.60) | No material change |
| Whole benchmark process, JIT off/on | 2194.77 (91.47) | 1974.67 (145.29) | Observed lower median; includes setup and mixed cold/warm work |

These results support selective lazy imports and simpler comprehensions. They
do not justify enabling JIT for every validation command. Historical reports
retain source hashes, interpreter version strings, samples, dispersion, and
preserved findings. Their JIT report predates schema 2's fuller build/dependency
identity and paired-effect fields; the table retains its original measurements.

An isolated free-threaded 3.15.0 build was also evaluated with the same minimal
dependencies: research-repo-tools 0.1.9, PyYAML 6.0.3, packaging 26.3, and
rust-just 1.58.0. Each batch planned 48 independent inputs over 1,305 fixture
paths. Inputs were copied and the lifecycle prepared before timing, excluding
initial control-file publication. Seven alternating subprocesses per variant
each supplied three samples after an excluded warmup. Executor scheduling was
included. Complete serialized plans matched across all jobs and modes; the GIL
state was checked after imports and operations.

| Interpreter mode | One thread, ms (MAD) | Two threads, ms (MAD) | Four threads, ms (MAD) |
| --- | ---: | ---: | ---: |
| Normal build | 645.77 (3.43) | 642.42 (5.10) | 649.22 (5.91) |
| Free-threaded build, GIL enabled | 708.59 (1.22) | 704.18 (1.76) | 709.73 (2.49) |
| Free-threaded build, GIL disabled | 708.34 (4.45) | 377.19 (3.27) | 204.69 (0.87) |

Four workers gave about 3.5 times the independent-plan throughput of one worker
on the same free-threaded build. Single-thread execution was slower than the
normal build; those builds also differ in compilation. This identifies a useful
future option for independent CPU batches. The actual graph runtime still uses
its existing process/artifact coordination; concurrent publication and live
validator integration were not established by this experiment. Free-threading
is not selected for the repository's default environment.

The Semgrep policy now has three additional repository-specific guards:

- Module-local lazy declarations are allowed; global `all` settings in Python
  scripts are rejected because they previously broke dependency initialization.
- Skill metadata must select a safe Python or C YAML loader, including dynamic
  `getattr` selection. This covers constructor paths outside Ruff's `yaml.load`
  check.
- Literal blanket `PYTHON_JIT=1` exports in the Justfile are rejected; explicit
  per-command benchmarks remain allowed.

The duplicate workflow-only `uv sync --locked` rule was removed. The existing
locked-command rule covers both `run` and `sync`, with all former workflow
mutation pairs retained. Production-path probes cover scripts, skill scripts,
Just, shell, workflows, aliases, and excluded tests/docs. Fixture counts enforce
four global lazy-mode violations, twelve unsafe loader selections, four blanket
JIT settings, and all six unlocked workflow run/sync commands. Existing rules
retain distinct repository contracts; SHA pinning and dangerous triggers remain
owned by zizmor, and general Python syntax/types by Ruff and ty.

## Validation

The counts below describe the adoption experiments before the branch review
repairs. Current reviewed-source validation and native CI status are recorded
in the branch review evidence and its eventual PR checks.

The initial native macOS `just ci` run passed 24 early contract tests and 1,907
remaining tests, with two platform-specific skips. Ruff formatting/lint,
strict ty, skill metadata, Semgrep scans/fixtures, workflow audits, shell,
TOML, YAML, and Markdown gates all passed. The 470 selected source files
retained their hashes throughout that run.

After the additional lazy imports, unpacking, metadata types, benchmark helper,
and Semgrep policy changes, the final native macOS `just ci` run passed 24 early
contract tests and 1,926 remaining tests (1,950 total). The two skips cover the
native Windows executor-shell case and a native Linux invalid-UTF-8 filename
case. All 475 selected source files retained their hashes during the run. All
static and fixture gates passed, including 19 added regression cases. The
working-tree and history secret scans again found zero findings. Only this
validation-note update followed the run; Markdown was checked again afterward.

A separate isolated run passed 99 checks covering both Python and C YAML
loaders plus the lazy-import/serialization contract. `just security` found
zero dependency vulnerabilities and zero secrets in history or the working
tree. Tracing produced a readable profile; sampling remained blocked by host
process-inspection permissions. Native Linux and Windows CI results remain
pending; local macOS success does not establish those matrix cells.

## Platform and updater boundaries

Semgrep 1.180.0 requires `pywin32==311` on Windows. Its published wheels stop
at Python 3.14; the Windows-only uv override uses 312's cp315 wheels. Remove the
override when Semgrep advances its pin. The lock resolves across supported
platforms, and CI exercises the native Windows Semgrep entry point. Local
macOS validation cannot establish a native Windows or Linux result.

Hosted Dependabot's uv updater currently rejects the 3.15 floor, as recorded
by the [upstream v0.1.9 release](https://github.com/acgetchell/research-repo-tools/releases/tag/v0.1.9).
Python version-update PRs are paused with `open-pull-requests-limit: 0`, which
[preserves security-update policy](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/customizing-dependabot-security-prs).
That runtime limitation can also affect security PR creation; the required
OSV audit continues. The published manual updater also loses project overrides
in its isolated resolver, which previously downgraded Semgrep. The local recipe
now stops before that step while the Windows override is present; see the
[project-aware manual refresh instructions](shared-tooling.md).
Restore the limit to 10 after a hosted 3.15 update succeeds. GitHub Actions
updates and the separately pinned approval workflow remain enabled.
