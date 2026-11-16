---
name: python-simplification-review
description: "Prune redundant Python code, tests, and fixtures when simplification or suite reduction is requested or duplication is material, preserving supported behavior and regression evidence."
---

# Python Simplification Review

Reduce the maintenance cost of Python code and its test suite through justified
deletion and consolidation. Optimize for a smaller set of clear responsibilities
and useful behavioral checks, not a target line count, test count, or coverage
percentage. A justified decision to keep code is a valid outcome.

## Scope And Ownership

Use the supplied scope; otherwise inspect the requested diff and the callers,
fixtures, and contract owners needed to judge it. Review an entire repository
or test suite when requested. Review requests are read-only; requests to simplify
or prune include relevant local edits and safe validation, not Git mutations or
publication.

Own deletion and consolidation decisions here. Use `python-test-quality` for
evidence design and isolation concerns, `python-api-design` for material public
interface changes, and `python-scientific-review` for mathematical or numerical
equivalence. Reuse existing specialist evidence rather than repeating reviews.
Before changing Python code, tests, or fixtures, apply
`python-build-portability`, including its Windows reference when supported.

## Establish What Must Survive

Read repository instructions, support policy, public interfaces, test selection,
and relevant historical regressions before proposing removal. Trace uses beyond
direct calls: imports and re-exports, entry points, plugin registration, dynamic
lookup, serialization, fixtures, and documentation examples. A search with no
callers is not proof that a public or dynamically loaded object is unused.

Identify concrete candidates and classify each as `Delete`, `Consolidate`,
`Simplify`, or `Keep`. State the retained behavior and evidence supporting the
decision. Prioritize candidates that remove recurring maintenance or execution
cost; avoid cataloging every unchanged helper. If evidence is incomplete, keep
the candidate and name the unresolved dependency or contract.

## Production Code

Look for unused private paths, duplicate transformations, pass-through wrappers,
obsolete compatibility shims, speculative extension points, redundant state, and
custom machinery already served by an established dependency or standard library.
Prefer deletion or a direct expression before introducing another abstraction.
A small amount of straightforward duplication may be clearer than a configurable
framework. Keep helpers that name a useful concept or enforce an invariant even
when they have one caller.

Check equivalence at observable boundaries: return shapes, exception categories
and timing, side effects, ordering, mutation, aliasing, lazy evaluation, resource
cleanup, cancellation, and supported version/platform behavior. Removing repeated
validation is safe only if trusted construction and later mutation cannot bypass
the retained check. Preserve security boundaries, rollback, and numerical behavior.
Do not remove compatibility code solely because the local interpreter no longer
needs it, or silently retire a public API as cleanup.

## Tests And Fixtures

For each proposed test deletion or merge, identify the scenario, oracle,
observable outcome, failure mode, and configuration it protects, then name the
retained test or case that provides that evidence. Similar names, shared covered
lines, and a green reduced suite do not establish redundancy.

- Delete duplicate scenarios and weak smoke checks only when retained evidence
  covers the same contract at the relevant boundary. Tests for explicitly retired
  behavior may go when that retirement is within the authorized scope.
- Preserve distinct historical bug inputs, rejection categories, numerical
  boundaries, platforms, optional dependencies, and interactions. Property tests
  do not automatically replace a fixed regression example or independent oracle.
- Consolidate repeated setup and finite case tables when assertions remain clear.
  Keep case identities and failure diagnostics. Avoid Cartesian parametrization
  for combinations with no distinct behavior, giant conditional tests, and fixture
  factories more complicated than the setup they replace.
- Remove assertions tied only to incidental implementation details when stronger
  observable evidence protects the behavior. Preserve interaction assertions when
  ordering, resource use, or external effects are themselves the contract.
- Put repetitive pure-logic cases at the smallest stable owning seam while
  retaining integration checks for wiring, real files/processes, installed imports,
  and failure propagation. Mocks do not replace those boundaries.
- Remove fixtures and dependencies made unused by accepted deletions after checking
  discovery, autouse fixtures, plugin hooks, and indirect parametrization. Keep
  mutable state isolated; wider fixture scope is not automatically simpler.

For expensive setup or test selection, use the existing
[runtime and selection guidance](../python-test-quality/references/runtime-and-selection.md).
Distinguish measured cost from inference; fewer collected cases alone do not prove
a speedup. Never prune a failing legitimate regression to obtain a passing run.

## Validate And Report

Implement authorized, high-confidence reductions in coherent groups. Use existing
repository checks and the parent validation ledger when provided. Verify retained
tests are still collected and exercise affected behavior; run relevant lint/type
checks and required gates. Reuse current evidence and rerun when a relevant edit
invalidates it. For a non-obvious coverage substitution, use a focused fault or
known regression reproduction when practical to show the retained check detects
the failure. Passing tests alone do not prove equivalence.

Report concrete deletions and consolidations, why retained evidence is sufficient,
validation performed, and unresolved candidates. Distinguish reduced boilerplate
from reduced execution cost. Use source locations and retained test names for
reviewable decisions; do not generate a second inventory of the whole suite.
Follow a supplied parent result contract when dispatched.

Review outcomes: [typed contract](../review-graph/references/typed-results.md); read on rejection. Missing evidence stays blocked.
