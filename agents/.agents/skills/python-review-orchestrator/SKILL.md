---
name: python-review-orchestrator
description: "Coordinate multi-pass Python reviews by selecting individual specialists for packaging and portability, notebooks, CLI behavior, boundary parsing, scientific code, support tooling, tests, and production integration. Use for changed, staged, branch, PR, release-readiness, repository-wide, or fix-all Python work spanning multiple concerns. Use a focused Python skill directly for a single concern."
---

# Python Review Orchestrator

Coordinate focused Python skills without copying their guidance. Select each skill independently from the changed behavior; selecting a pass does not imply loading every skill listed in that pass.

## Ground Rules

- Do not mutate git state unless the user explicitly requests it in the current turn.
- Respect repository-local instructions before inspecting or editing files.
- Prefer changed-file scope. Use whole-repository mode only when explicitly requested or handed off as baseline scope by `repo-review`.
- Honor a parent orchestrator's branch-scope file list instead of narrowing it to current worktree changes.
- When asked to fix issues, implement safe actionable fixes as each pass finds them.
- Use focused validators while iterating. Run full CI only when repository policy or cross-layer risk requires it.
- Maintain one cross-skill validation ledger keyed by source/environment state,
  built artifact and installation-target identity, Python/platform/dependency
  configuration, instrumentation, and exact test selection. Use a wheel,
  sdist, installed tree, or entry-point digest when applicable. Reuse
  still-valid evidence instead of replaying it through broader recipes.

## Establish Scope And Routing

1. Inspect the supplied scope. Otherwise use read-only git commands to enumerate
   the committed branch delta from its merge base, staged changes, unstaged
   changes, and untracked paths.
2. Read the complete contents of every untracked file with a file-appropriate
   reader before selecting skills; a status entry or filename is not evidence.
3. Read [`references/check-routing.md`](references/check-routing.md).
4. Select individual skills from changed behavior, not file extensions alone.
5. State selected and meaningfully skipped skills before loading specialist bodies.
6. Load a repository-specific reference only when both the repository and its concern match.

Validator selection is independent from skill selection. Running tests for changed code does not by itself require loading `python-test-quality`.

## Review Trace

For each selected skill, record:

- why it applies
- skill and reference files loaded
- changed files inspected
- findings or explicit no-finding outcome
- fixes applied
- focused validation and result, or the matching ledger evidence reused

When invoked by `repo-review`, provide table-ready evidence for the parent review. Name selected and skipped skills whose absence might otherwise appear accidental.

## Pass Order And Individual Selection

Run applicable skills in this order. Within a pass, select only the skills whose trigger conditions match.

### 1. Build, Install, And Configuration

- Select `python-build-portability` for package builds, wheels, sdists, package discovery/data, entry points, extras, environment markers, declared Python or platform support, editable-versus-installed differences, optional imports, native extensions, or external consumers.
- Select `project-tooling-review` separately when workflow mechanics, command recipes, validation configuration, installers, or tool-version pins changed. Do not load it merely because package source changed.

### 2. Notebook And Reproducibility

- Select `jupyter-notebook-review` for `.ipynb` structure, cell identity, hidden state, outputs, notebook environments, plotting, headless execution, or generated notebook artifacts.
- Select additional Python specialists only when notebook cells contain substantial behavior owned by those skills. Plotting already-produced data does not automatically require scientific review.

### 3. Application And Boundary Behavior

- Select `python-cli-review` for user-visible CLI/application contracts, arguments, stdout/stderr, privacy-sensitive output, application file workflows, and date/time behavior.
- Select `python-parse-dont-validate` independently for raw dictionaries, config, environment variables, structured files, subprocess output, paths, optionals, primitive values with invariants, or validated domain models.

Do not load `python-cli-review` for a pure parser or model change with no application behavior. Do not load the parsing skill for passive data shapes with no meaningful invariant.

### 4. Scientific And Data Correctness

- Select `python-scientific-review` for mathematical, numerical, geometric, statistical, stochastic, dataframe-computation, scientific-reproducibility, or independent Rust-interoperability behavior.
- Select the parsing skill additionally only when external scientific inputs carry structural or domain invariants before computation.

### 5. Development And Release Support

- Select `python-support-scripts` for changelog generators, release helpers, benchmark runners, CI utilities, fixture generators, diagnostic tools, generated-artifact preparation, or subprocess orchestration around development tools.
- Add CLI or parsing skills only when their distinct contracts are material; a support script having `argparse` does not alone require a second full pass.

### 6. Test Evidence

Select `python-test-quality` when:

- tests, fixtures, pytest configuration, or test helpers changed
- the user requests test or coverage review
- a discovered bug requires regression evidence
- property, stateful, async, subprocess, install, or configuration-matrix evidence is a material part of the contract
- existing tests may conceal a production defect through weak assertions, excessive mocking, nondeterminism, or duplicated logic

Skip the skill when tests are unchanged and specialist validation is sufficient. Still run appropriate focused tests.

### 7. Production Synthesis

Always load `python-production-review` after selected specialists in orchestrated work. Use its orchestrated mode: do not load the standalone checklist.

Use it to review ordinary reusable Python code with no narrower owner, reconcile cross-skill contracts, remove duplicate findings, inspect residual integration/resource/security risks, and decide release readiness.

## Per-Skill Fix Loop

For each selected specialist:

1. Announce the skill and why it applies.
2. Read its `SKILL.md` completely and only directly relevant references.
3. Inspect the changed surface and nearby contract owners.
4. Record findings or an explicit no-finding result.
5. Implement minimal fixes when authorized.
6. Run the smallest validator that covers the risk only when equivalent evidence is not already valid in the shared ledger.
7. Fix validator failures before continuing or document a genuine blocker.

Do not claim an orchestrated review from one undifferentiated pass. Preserve ownership and evidence per selected skill.

## Final Summary

Lead with unresolved blockers. Then include:

- files changed and why
- selected skills and references actually loaded
- meaningful skips
- fixes and cross-skill reconciliations
- the non-overlapping validation ledger and results
- untested configurations or external limitations
- confirmation that git state was not mutated, when true

When invoked by `repo-review`, return this evidence in the parent's requested table-ready form.
