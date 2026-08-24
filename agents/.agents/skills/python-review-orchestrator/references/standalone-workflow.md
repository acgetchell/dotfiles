# Standalone Python Review Orchestration

Read this reference completely only for a directly requested Python
orchestration outside `review-graph` routing mode.

## Ground Rules

- Prefer changed-file scope. Use whole-repository mode only when explicitly
  requested or supplied as a parent baseline scope.
- Honor a parent orchestrator's branch-scope file list instead of narrowing it
  to current worktree changes.
- When asked to fix issues, implement safe actionable fixes as each pass finds
  them.
- Use focused validators while iterating. Run full CI only when repository
  policy or cross-layer risk requires it.
- Maintain one cross-skill validation ledger keyed by source/environment state,
  built artifact and installation-target identity, Python/platform/dependency
  configuration, instrumentation, and exact test selection. Use a wheel,
  sdist, installed tree, or entry-point digest when applicable. Reuse
  still-valid evidence instead of replaying it through broader recipes.

## Establish Scope And Routing

1. Inspect the supplied scope. Otherwise use read-only git commands to enumerate
   the committed branch delta from its merge base, staged changes, unstaged
   changes, and untracked paths.
2. Read every untracked file completely with a file-appropriate reader before
   selecting skills; a status entry or filename is not evidence.
3. Read [`check-routing.md`](check-routing.md).
4. Select individual skills from changed behavior, not file extensions alone.
5. State selected and not-selected skills with reasons before loading
   specialist bodies.
6. Load a repository-specific reference only when both the repository and its
   concern match.

Validator selection is independent from skill selection. Running tests for
changed code does not by itself require loading `python-test-quality`.

## Review Trace

For each selected skill, record why it applies, skill and reference files
loaded, changed files inspected, findings or an explicit no-finding outcome,
fixes, and focused validation or matching ledger evidence reused.

When a caller supplies an established scope, begin with a handoff receipt
naming the supplied scope and selected and not-selected skills, then provide
table-ready evidence. Name not-selected skills whose absence might otherwise
appear accidental.

## Pass Order And Individual Selection

Run applicable skills in this order, selecting only skills whose triggers
match.

### 1. Build, Install, And Configuration

- Select `python-build-portability` for package builds, wheels, sdists, package
  discovery and data, entry points, extras, environment markers, declared
  Python or platform support, editable-versus-installed differences, optional
  imports, native extensions, or external consumers.
- Select `project-tooling-review` separately for workflow mechanics, command
  recipes, validation configuration, installers, or tool-version pins.

### 2. Notebook And Reproducibility

- Select `jupyter-notebook-review` for `.ipynb` structure, cell identity, hidden
  state, outputs, notebook environments, plotting, headless execution, or
  generated notebook artifacts.
- Select additional Python specialists only when cells contain substantial
  behavior they own. Plotting existing data does not automatically require
  scientific review.

### 3. Application And Boundary Behavior

- Select `python-cli-review` for user-visible application contracts, arguments,
  output channels, privacy-sensitive output, file workflows, and date/time
  behavior.
- Select `python-parse-dont-validate` independently for raw dictionaries,
  configuration, environment values, structured files, subprocess output,
  paths, optionals, primitive invariants, or validated domain models.

Do not load the CLI skill for a pure parser/model change or the parsing skill
for passive shapes with no meaningful invariant.

### 4. Scientific And Data Correctness

- Select `python-scientific-review` for mathematical, numerical, geometric,
  statistical, stochastic, dataframe-computation, scientific-reproducibility,
  or independent native-interoperability behavior.
- Add the parsing skill only when external scientific inputs carry invariants
  before computation.

### 5. Development And Release Support

- Select `python-support-scripts` for changelog, release, benchmark, CI,
  fixture, diagnostic, generated-artifact, or development subprocess behavior.
- Add CLI or parsing skills only when their distinct contracts are material;
  `argparse` alone does not require another pass.

### 6. Test Evidence

Select `python-test-quality` when tests, fixtures, pytest configuration, or
helpers changed; test or coverage review was requested; a bug requires
regression evidence; property, stateful, async, subprocess, install, or matrix
evidence is material; or weak assertions, mocking, nondeterminism, or duplicated
logic may conceal a defect.

Skip it when tests are unchanged and focused specialist validation is
sufficient. Still run appropriate focused tests.

### 7. Production Synthesis

Always load `python-production-review` after selected specialists in
orchestrated work. Use orchestrated mode without the standalone checklist. It
owns ordinary reusable Python with no narrower owner, cross-skill
reconciliation, duplicate removal, residual integration/resource/security
risk, and the readiness verdict.

## Per-Skill Fix Loop

For each selected specialist:

1. Announce the skill and why it applies.
2. Read its `SKILL.md` completely and only directly relevant references.
3. Inspect the changed surface and nearby contract owners.
4. Record findings or an explicit no-finding result.
5. Implement minimal fixes when authorized.
6. Run the smallest risk-covering validator only when equivalent evidence is
   not already valid in the shared ledger.
7. Fix validator failures before continuing or document a genuine blocker.

Do not claim orchestration from one undifferentiated pass. Preserve ownership
and evidence per selected skill.

## Final Summary

Lead with unresolved blockers. Include files changed, selected skills and
references, meaningful skips, fixes and reconciliations, the non-overlapping
validation ledger, untested configurations or external limitations, and git
state. Return table-ready evidence when a parent requests it.
