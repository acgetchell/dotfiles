# Python Review Routing

Apply this matrix to the selected scope, including unchanged contracts in a whole-package baseline. Select skills individually and choose validators separately.

## Scope Detection

Use a supplied parent scope when present. For a whole-package baseline,
inventory the package and its supporting files, including unchanged paths.
For changed-file reviews, use read-only git commands to enumerate the
committed branch delta from its merge base, staged changes,
unstaged changes, and every untracked path. Read the complete contents of each
untracked file with a file-appropriate reader before routing it; a status entry
or filename alone is insufficient. Classify the resulting complete scope by
behavior:

- Python modules, scripts, and type stubs
- pytest tests, fixtures, and configuration
- notebooks and notebook helpers
- packaging, dependency, uv, Ruff, ty, and runtime metadata
- scientific data, examples, and generated artifacts
- workflow, recipe, and documentation surfaces shared with other orchestrators

## Individual Skill Routing

For a change review, select each row whose contract the change affects. For a
whole-package baseline, select each row whose contract the package contains,
including unchanged APIs, commands, scientific code and tests. Account for
each captured path through an assigned reviewer, matching prior review evidence
or a documented scope exclusion. In graph mode, use the parent's
[captured-path accounting rules](../../review-graph/references/planning-contract.md).

Run selected rows in contract-dependency order. Establish build and platform constraints early, use domain and test evidence before pruning, and finish with production synthesis. Record an explicit style decision for every scope.

| Skill | Select when | Skip when |
|---|---|---|
| `python-build-portability` | Whole-package baseline (inspect build/install and supported-platform evidence regardless of staged diff), wheels, sdists, package discovery/data, installed imports, entry points, extras, markers, supported runtimes/platforms, native extensions, external consumers; platform-sensitive scripts and fixtures, including unpackaged tooling | Changed-file scope covers only workflow commands or tool pins and no Python platform contract is affected |
| `python-style-hygiene` | Python source, tests, stubs, or code examples (including documentation) are in scope, even when lint passes. | The scope contains no Python code or examples. |
| `python-api-design` | Material public or cross-module concepts, imports/exports, callable signatures, return shapes, protocols, callbacks, stubs, extension hooks, or compatibility | Private helpers with no material shared caller contract |
| `jupyter-notebook-review` | Notebook cells, metadata, outputs, execution, plotting, environments, or notebook artifacts | A normal Python module merely supports a notebook |
| `python-cli-review` | User-visible command arguments, output, privacy, application files, dates/times, or exit behavior | Only parser/model or support-transform internals are in scope |
| `python-parse-dont-validate` | Raw external values carry structural or semantic invariants into trusted code | Passive reports or already-validated values |
| `python-scientific-review` | Mathematical, numerical, statistical, geometric, stochastic, dataframe-computation, or scientific-oracle behavior | Plot formatting or generic file plumbing only |
| `python-support-scripts` | Release, changelog, benchmark, CI, fixture, diagnostic, generated-artifact, or development subprocess behavior | User application or scientific algorithm code |
| `python-test-quality` | Tests, fixtures, test helpers, or pytest configuration are in scope, coverage/test review was requested, a bug needs regression evidence, or assertions, isolation, install or platform coverage are at risk | No selection trigger applies and focused specialist validation supplies sufficient evidence |
| `python-simplification-review` | Pruning or suite reduction is requested; redundant code, tests, fixtures, wrappers, compatibility paths, or accidental complexity are material | No concrete deletion or consolidation opportunity and no simplification request |
| `python-production-review` | Always select for final synthesis, including when the Python orchestrator is invoked directly. Run after any selected specialists and reconcile findings, ordinary modules, integration risks and readiness | Required even when no narrower specialist applies |

Select `project-tooling-review` outside this skill when recipes, workflows, validation configuration, installers, or tool versions are in scope. Select documentation review for suite-wide docs consistency. Shared ownership does not justify loading unrelated Python specialists.

For PRs or platform-sensitive changes, apply
[platform coverage and native CI](../../review-graph/references/platform-ci-review.md)
before selecting validators and again before completion. Read unchanged CI
workflows to discover where changed scripts/tests run. Windows execution makes
path, shell, subprocess, and fixture assumptions relevant even when changed
files contain no `sys.platform` branch. Consult the portability owner and the
applicable support/test platform references; record actual reads, not only
selected skill names.

## Focused Validators

Prefer repository commands. Otherwise choose the smallest applicable evidence:

| Surface | Focused evidence |
|---|---|
| Python source | Compile/import check, `uv run --locked ruff check`, `uv run --locked ruff format --check`, `uv run --locked ty check`, targeted pytest |
| Public API/stubs | Representative public imports and caller expressions, configured type checks, affected runtime tests; installed consumers through portability when needed |
| CLI | Targeted tests plus safe `--help` or entry-point smoke check |
| Parser/model | Rejection and acceptance tests plus `uv run --locked ty check` |
| Scientific | Targeted numerical/property/fixture tests; benchmark only for performance claims |
| Support script | Fixture/golden tests and safe `--help` smoke check |
| Notebook | Structured lint; execute only when runtime behavior or artifacts are in scope |
| Build/install | `uv lock --check`, `uv build`, isolated uv wheel install, external import, entry points/extras |
| Tests only | Narrow pytest target or repository test recipe |
| Docs/examples | Documentation and example validators |
| Workflow/config | Tooling-owned YAML, action, lock, lint, or configuration validators |

When annotations or invariant models change, run ty through uv. Use Ruff through uv for lint and format evidence. Before running a validator, record its source/environment state, built artifact and installation-target identity, Python/platform/dependency configuration, instrumentation, and exact test selection in the shared ledger. Reuse build/install or external-consumer evidence only when the artifact and installation target also match. When a validator fails, fix and rerun it after that repair invalidates the prior result before moving to the next skill, or document the blocker.

## Escalate To Full CI

Run full CI when the user explicitly requests it, repository policy requires it, changes span several Python layers without a narrower combined validator, public behavior and packaging changed together, scientific results have broad impact, or final synthesis identifies uncovered cross-cutting risk. Do not run it solely because orchestration is ending.

Inspect a known required gate's composition before choosing validators. Use
focused red/green regression checks for prompt feedback during a fix, then run
the required full gate on the final source state even when it repeats those
tests. Record the overlapping selections and the reason in the shared ledger;
repeated executions are not independent coverage evidence.

- **Full gate known before review:** if the user requires `just ci` and review
  exposes a regression, reproduce it with the narrow test, fix it, and rerun
  that test immediately. Complete `just ci` after the fixes and record the
  overlap as focused fix feedback followed by the required final gate.
- **Full gate requested after focused checks:** run the newly requested gate,
  including an indivisible gate with overlapping tests. Record the user's
  request as the reason for overlap; no additional approval or command-surface
  blocker is needed merely because focused evidence already exists.

Avoid gratuitous case-to-module-to-suite reruns. When no full gate is required,
reuse current evidence and run only uncovered validators. A relevant edit
invalidates earlier evidence; a desire for a broader summary does not. Reserve
command-surface blockers and `project-tooling-review` routing for validation
that is genuinely unavailable or unsatisfiable, not unavoidable overlap.

## Handoff Evidence

Report selected and meaningfully skipped skills, files inspected, references loaded, findings/fixes, the shared validation ledger and results, configuration gaps, and git-state status. Keep evidence attributable to individual skills.
