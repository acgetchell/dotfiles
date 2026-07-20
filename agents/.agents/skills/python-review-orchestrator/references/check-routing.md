# Python Review Routing

Use this matrix after identifying changed behavior. Select skills individually and choose validators separately.

## Scope Detection

Use a supplied parent scope when present. Otherwise inspect read-only status and diffs. Classify files by behavior:

- Python modules and scripts
- pytest tests, fixtures, and configuration
- notebooks and notebook helpers
- packaging, dependency, uv, Ruff, ty, and runtime metadata
- scientific data, examples, and generated artifacts
- workflow, recipe, and documentation surfaces shared with other orchestrators

## Individual Skill Routing

| Skill | Select when | Skip when |
|---|---|---|
| `python-build-portability` | Wheels, sdists, package discovery/data, installed imports, entry points, extras, markers, supported runtimes/platforms, native extensions, external consumers | Only workflow commands or tool pins changed |
| `jupyter-notebook-review` | Notebook cells, metadata, outputs, execution, plotting, environments, or notebook artifacts changed | A normal Python module merely supports a notebook |
| `python-cli-review` | User-visible arguments, output, privacy, application files, dates/times, or exit behavior changed | Pure parser/model or support-transform change |
| `python-parse-dont-validate` | Raw external values carry structural or semantic invariants into trusted code | Passive reports or already-validated values |
| `python-scientific-review` | Mathematical, numerical, statistical, geometric, stochastic, dataframe-computation, or scientific-oracle behavior changed | Plot formatting or generic file plumbing only |
| `python-support-scripts` | Release, changelog, benchmark, CI, fixture, diagnostic, generated-artifact, or development subprocess behavior changed | User application or scientific algorithm code |
| `python-test-quality` | Test artifacts changed, coverage/test review was requested, or durable evidence is itself at risk | Tests are unchanged and focused specialist validation is sufficient |
| `python-production-review` | Always in orchestrated mode; also owns ordinary reusable modules and residual integration concerns | Never skip final synthesis during orchestration |

Select `project-tooling-review` outside this skill when recipes, workflows, validation configuration, installers, or tool versions changed. Select documentation review for suite-wide docs consistency. Shared ownership does not justify loading unrelated Python specialists.

## Common Combinations

- Pure config parser: parsing, then production; add test-quality only for changed or materially weak evidence.
- CLI importing structured data: CLI plus parsing, then production.
- Scientific computation over external data: parsing plus scientific, then production.
- Scientific notebook plotting existing artifacts: notebook, then production; add scientific only when cells perform or validate scientific computation.
- Release script with a user-facing CLI: support scripts; add CLI only for a substantial public output/argument contract.
- Packaging metadata or installed import change: build portability, then production; add tooling only for command or workflow mechanics.
- Tests-only change: test quality plus the domain specialist only when the tests encode a domain assumption that could hide a production bug.
- Ordinary reusable module: production; add a focused specialist only for a matching concern.

## Focused Validators

Prefer repository commands. Otherwise choose the smallest applicable evidence:

| Surface | Focused evidence |
|---|---|
| Python source | Compile/import check, `uv run --locked ruff check`, `uv run --locked ruff format --check`, `uv run --locked ty check`, targeted pytest |
| CLI | Targeted tests plus safe `--help` or entry-point smoke check |
| Parser/model | Rejection and acceptance tests plus `uv run --locked ty check` |
| Scientific | Targeted numerical/property/fixture tests; benchmark only for performance claims |
| Support script | Fixture/golden tests and safe `--help` smoke check |
| Notebook | Structured lint; execute only when runtime behavior or artifacts are in scope |
| Build/install | `uv lock --check`, `uv build`, isolated uv wheel install, external import, entry points/extras |
| Tests only | Narrow pytest target or repository test recipe |
| Docs/examples | Documentation and example validators |
| Workflow/config | Tooling-owned YAML, action, lock, lint, or configuration validators |

When annotations or invariant models change, run ty through uv. Use Ruff through uv for lint and format evidence. Before running a validator, record its source/environment state, Python/platform/dependency configuration, instrumentation, and exact test selection in the shared ledger. Reuse equivalent still-valid evidence. When a validator fails, fix and rerun it after that repair invalidates the prior result before moving to the next skill, or document the blocker.

## Escalate To Full CI

Run full CI when repository policy requires it, changes span several Python layers without a narrower combined validator, public behavior and packaging changed together, scientific results have broad impact, or final synthesis identifies uncovered cross-cutting risk. Do not run it solely because orchestration is ending.

Decide whether repository policy or known cross-layer scope requires the full
gate before executing the first test, and inspect the gate's composition then.
If it contains tests already passing for the current
source/environment/configuration state, choose the full gate as the single
test selection from the outset or run only its uncovered validators. Do not
nest a named pytest case, its containing module or suite, and full CI. If a
mandatory indivisible gate is discovered late and offers no reliable
exclusion, report the command-surface blocker and route it to
`project-tooling-review`; do not silently replay tests or count them twice. A
relevant edit invalidates earlier evidence; a desire for a broader summary
does not.

## Handoff Evidence

Report selected and meaningfully skipped skills, files inspected, references loaded, findings/fixes, the shared validation ledger and results, configuration gaps, and git-state status. Keep evidence attributable to individual skills.
