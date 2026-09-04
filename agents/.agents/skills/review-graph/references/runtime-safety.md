# Review Graph Runtime Safety

Read this reference when materializing or retrying a graph, compiling a node,
coordinating a large ready set, diagnosing isolation, or expanding late
validation.

## Retry-Safe Materialization

The exact symbolic triple `["scope", "worktree", "repository"]` in the public
operation example means “use the plan-bound captured triple.” Materialization
resolves it only when planned validation units agree on one triple. It stages
the complete immutable file set outside the requested store, preflights every
conflict, and publishes only after all dispatches and contracts validate. A
CLI operation-result path must be outside the store. The runtime publishes that
result and the store with rollback on either failure, so a failed attempt leaves
both destinations retryable.

## Transactional Compilation

`compile-node --output` names the operation-result JSON, not the dispatch-owned
compiled artifact. All destinations must be distinct. The runtime preflights
them, publishes compiled evidence and the operation result, then appends the
journal event as the final acceptance commit.

## Isolation And Compact Readiness

For `fresh_context: true`, compilation rejects a command ledger that names
another node's worker input, payload, compiled report, or evidence sidecar.

Use `next-ready --compact` for large ready sets. It returns node IDs, result
contracts, execution locations, and immutable `worker_input_path` references
without embedding full dispatches.

## Late Validation Quality

Before expansion, the runtime checks Cargo benchmark target
`required-features`, requires a repository canonical `just` benchmark recipe
when one exists, checks non-isolated working directories against the captured
current state, and rejects post-remediation-only evidence in a review-only
source epoch.
