# Repo-Review Replacement Acceptance

Use this contract to decide whether `review-graph` remains a complete
replacement for the legacy grouped `repo-review` path.

## Deterministic Gate

Require on every repository change:

- every routing catalog skill resolves to one approved path whose frontmatter
  name matches the catalog skill ID
- every consulted router returns one disposition per catalog entry
- repository classifier signals are selected or explicitly conflict-resolved
- every selected leaf appears in the required graph or exact verified reuse
- no applicable skill is completion-satisfied by a budget skip
- every execution epoch preserves the worker reserve and complete node order
- late handoffs and post-fix rerouting are closed before synthesis
- baseline validation, applicable language synthesis, independent review for a
  concrete change, and repository synthesis are accepted
- all source fingerprints, node lifecycle equalities, and final report
  equalities reconcile

Run the routing-catalog, surface-matrix, planner, completion, acceptance,
failure/resume, and scope-capture tests in CI.

## Representative Matrix

Cover:

1. C++ build, API, scientific behavior, and tests
2. Rust source, public API, invariants, package metadata, and tests
3. Python packaging, CLI, scientific behavior, notebooks, scripts, and tests
4. Documentation suite, API docs, citations, scientific claims, and release
   metadata
5. Tooling/workflow-only changes
6. Cross-surface manifests, workflows, command docs, and shared ownership
7. Staged-only scope
8. Clean whole-repository baseline
9. Release-readiness active-document expansion
10. Review-and-fix invalidation, rerouting, revalidation, and synthesis
11. Worker failure, deadline exhaustion, and fresh-root epoch resumption

## Forward Gate

Require three consecutive accepted forward trials for each major mode:

- branch or pull-request read-only
- whole-repository baseline or release readiness
- review-and-fix

Also require one forced worker-creation failure/resume trial and one graph that
must continue across multiple fresh-root epochs.

Each trial must have:

- 100% applicable-skill recall against an independently adjudicated expected
  routing ledger
- zero silent omissions or unexplained extra owners
- every canonical actionable finding preserved; additional valid findings are
  allowed
- every selected node accepted or explicitly incomplete, never substituted by
  coordinator work
- complete validation, synthesis, fingerprint, lifecycle, and report evidence

Record trials in task artifacts rather than hard-coding repository-specific
results in this skill. A failing trial reopens the replacement gate until its
cause is fixed and the consecutive count restarts.

## Compatibility Policy

Keep `repo-review` as a thin graph-first entry point. Allow the legacy grouped
path only when the user explicitly requests `legacy-grouped`; never switch to
it silently after a graph blocker. Preserve the `Review Evidence` table as a
compatibility view derived from the graph ledger.
