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

## Artifact Write Review And Approval Retry

Before publishing a worker payload, pass its exact bytes over standard input to
the dispatch-bound review command. The runtime validates the schema and semantics
without an artifact write. For audits, `scope_limitations` must equal the omitted
`owned_paths`; `nearby_contract_owners` is inspected context provenance, not
omitted scope, and narrative `limitations` never expand the write set. Only the
published payload path is a durable artifact target; atomic publication uses a
runtime-owned temporary sibling. The stdin contract contains no candidate path.
Legacy `--payload` inputs retain a separate candidate-bearing schema for saved
dispatches.

The persistence receipt and any publication-failure diagnostic carry the same
`artifact_write_review`: exact byte digest/count, bound paths, path-role summary,
and a canonical digest of the entire validated persistence contract, including
mode, owned paths, and schema version. The `approval_identity` binds the bytes,
target, input mode, and contract digest. Both the stdin CLI and Python publication
API require this identity; it identifies the reviewed write and does not grant
environment permission. If the environment requires
explicit approval, keep the reviewed bytes unchanged and retry with
`--approval-identity <approved identity>`. The runtime rejects changed bytes or
paths or contract fields instead of treating a different write as approved.

## Live Worker Publication Smoke Test

After publication-contract changes, complement deterministic tests with one
fresh worker (`fork_turns: "none"`) and an external temporary proof store. Give
it only a materialized audit dispatch, its skill/instructions, a small owned
source fixture, and a nearby context fixture. Ask it to inspect both and publish
its own payload through the generated prompt. Record the context boundary as a
narrative limitation; let the worker classify path ownership and scope omissions.

Observe the actual tool/approval outcome, compare returned and persisted bytes,
and compile the payload through `compile-node` to journal acceptance. Record the
contract identity, any approval request, compiler result, and journal status in
the external test evidence. A subprocess or mocked filesystem test does not
establish the live approval outcome. This is a bounded publication test, not a
complete repository review.

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
