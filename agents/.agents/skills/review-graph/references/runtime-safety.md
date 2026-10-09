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
omitted scope, and narrative `limitations` never expand the write set. For payload
publication, the reviewed payload target is the published payload path; atomic
publication uses a runtime-owned temporary sibling. Publication also persists
the complete write-review evidence as an immutable digest-addressed sibling in
the proof store. The stdin contract contains no candidate path.
Source captures and other workflow proof artifacts remain authorized under the
external temporary store; the payload restriction does not prohibit those writes.
Legacy `--payload` inputs retain a separate candidate-bearing schema for saved
dispatches. New audit contracts include a digest-bound compiler preflight so
generated native output that exceeds section limits fails before publication.
Preflight dry-compiles with hypothetical equal captures; it does not attest to
execution. Actual capture verification still runs during compilation. Saved contracts
without preflight remain supported.

The read-only review command returns `native_size_preflight`: generated result
and section byte counts, their limits, and `scope_rendering` (`inline` or
`reference`). Use it before publication to diagnose remaining size failures.
When an audit's inline Scope Inspected would exceed the section limit, the
compiler keeps its complete payload at `expectation.canonical_worker_payload`
in the metadata artifact and renders counts plus digest-backed references.
The same artifact retains the complete audit input identity and coverage reuse
proof. Preserve all dependency paths and coverage partitions; compact rendering
does not require changing the worker payload or lifting native size limits.
Verification binds every reference and count, rederives normalized evidence,
and compares the canonical payload with sealed worker bytes when present.
Missing or changed bound metadata or sealed bytes fail verification. Smaller
audits and previously compiled inline reports retain their existing format.

Publication and persistence receipts default to compact status/identity fields
and `artifact_write_review_reference` (path, exact byte digest, and byte count).
The immutable reference contains the complete `artifact_write_review`: exact
payload byte digest/count, bound paths, path-role summary, and a canonical digest
of the entire validated persistence contract, including mode, owned paths, and
schema version. `--full-output` includes that review inline; Python publication
receipts retain it inline. The read-only `review-worker-payload-write` command
continues returning the complete review without writing artifacts.

Publication-failure diagnostics retain the error, actionable message, node,
payload identity, approval identity, and saved review reference without repeating
path inventories. If evidence storage itself fails, the reference is null and
the payload is not published. `--full-output` also includes the complete review
in rejection diagnostics. Changed or symlinked evidence sidecars cannot be
overwritten, and identical retries reuse the same saved evidence.
The `approval_identity` binds the bytes,
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
its own payload through the generated prompt. Let the worker classify inspected
context in `nearby_contract_owners`, omissions in `scope_limitations`, and known
execution context in `execution_facts`. Preserve actual unresolved or
unclassified caveats in their blocking fields.

Observe the actual tool/approval outcome, compare returned and persisted bytes,
and compile the payload through `compile-node` to journal acceptance. Record the
contract identity, any approval request, compiler result, and journal status in
the external test evidence. A subprocess or mocked filesystem test does not
establish the live approval outcome. This is a bounded publication test, not a
complete repository review.

## Isolation And Compact Readiness

For `fresh_context: true`, compilation rejects a command ledger that names
another node's worker input, payload, compiled report, or evidence sidecar.

Default CLI receipts include node IDs, result contracts, execution locations,
and digest-bound `worker_input` references without embedding full dispatches.
Read `output.path` for complete saved results, or use `--full-output` for diagnostic
stdout. `next-ready --compact` also compacts the saved ready-list artifact;
complete immutable worker inputs and proof records remain available.

## Late Validation Quality

Before expansion, the runtime checks Cargo benchmark target
`required-features`, requires a repository canonical `just` benchmark recipe
when one exists, checks non-isolated working directories against the captured
current state, and rejects post-remediation-only evidence in a review-only
source epoch.

## Compact Transport

Bootstrap binds capture identities with JSON-path diagnostics and saves complete
stage inputs. Its default stdout receipt includes `output.path` and `output.digest`,
blockers, node count, and a directly executable `next_command` argument array.
Pass the saved bootstrap bundle directly to `materialize-dispatches`; no nested
JSON extraction is needed. `next_command` is null when the plan is blocked.
`review_graph_plan.py --input` remains a full-plan diagnostic.

Bootstrap and artifact-producing runtime operations print compact receipts by
default. Read the named artifacts only when their contents are needed; the
receipt does not replace any proof artifact. `--full-output` prints the complete
operation result for diagnosis. Publication and journal commands retain their
already compact transaction/event receipts. `materialize-dispatches` and
`next-ready` return per-node contract/location and digest-bound `worker_input`
references rather than embedding dispatch bodies. Full artifacts remain on disk.

Planned-validation identities live once in read-only, content-addressed JSON
sidecars. Workers receive `execution_identity_reference` (path and digest), a
small `execution_summary`, requirement/unit IDs, and `planned_validation_digest`.
Use those IDs/digests in review requests. Read the full identity only when needed;
the compiler always resolves it, checks the full digest and summary, and retains
all captured paths and execution invariants. Missing, changed, or symlinked
sidecars fail verification. Embedded full-identity dispatches are no longer accepted.

## Independent Review Format

Independent workers default to `compact-independent-review`: JSON matching the
materialized schema and [blocked starter template](independent-payload-template.json).
Supply observed fingerprints, command/mutation attestations, findings/handoffs,
and substantive evidence with inspected paths for each dispatched stable check ID:
`fallback`, `platform`, `parser-errors`, `unexpected-exceptions`, `test-boundaries`.
Required checks vary with scope. Never fill an unperformed check to satisfy the
schema; return blocked with truthful limitations. Nonblank evidence is a
structural requirement, not a machine proof that the judgment is correct.

Keep `files_inspected` exactly dispatch-owned. Record necessary dependency/context
reads in optional `nearby_contract_owners`; adversarial `inspected_paths` remain
owned-only. `git_dependencies` uses the same
exact-command and conservative classification rules as audits. The canonical
payload retains this provenance. Independent inputs remain conclusion-blind.

Before publication, the bound compiler preflight rejects missing/duplicate/unknown
checks, empty evidence, scope errors, mismatched captures, and prohibited commands.
The compiler renders the six native sections and labels, binds the canonical
payload, then applies the existing target/path, line-bound, fingerprint, finding,
handoff, and native-evidence verification. `compile-node` seals the exact published
bytes, checks actual captures, and journals only verified evidence.

Independent-review publication and compilation accept structured JSON only.
The runtime generates native proof reports; reviewer-authored native inputs and
embedded full validation identities are rejected. Rematerialize older dispatches.

## Journal And Fallback

`journal-append` serializes `in-flight`, `accepted`, `blocked`, `invalidated`,
and terminal `awaiting-replan` states; acceptance requires compiled evidence.
Its CLI field contract is:

| Status | Artifact + metadata | Kind | Reason |
| --- | --- | --- | --- |
| `in-flight` | forbidden | forbidden | forbidden |
| `accepted` | required | optional with evidence | forbidden |
| `blocked` | optional as a pair | optional with evidence | required |
| `invalidated` | forbidden | forbidden | required |
| `awaiting-replan` | forbidden | forbidden | required |

Reserve ready dispatches; append `in-flight` only after creation succeeds.
Final results may not release capacity immediately. On capacity-only failure,
retain the reservation, wait at most 30 seconds for progress, and retry once
when capacity is uncertain or a creation race occurred.
Then record attempts and apply profile fallback/resume. Never probe with
throwaway workers, replay accepted work, or claim execution without a worker.

For grouped audits, `schedule-ready` accepts an optional `creation_failure` with
the exact unstarted worker `node_id`, `failure_kind` (`capacity` or `unexpected`),
`attempts` (1 or 2), observed `reason`, and `worker_created: false`. It preserves
the diagnostic in its immutable continuation. A first capacity failure with
uncertain or available slots returns `bounded-retry` and `retry_after_seconds: 30`;
wait for progress up to that bound before the unchanged dispatch's sole retry.
Known exhaustion, a second capacity failure, or an unexpected error selects
`coordinator-fallback` without a capacity wait. Execute only returned selected
dispatches: when the coordinator lane is occupied, retain the failure for the
next request. Other node failures use the existing profile fallback/resume path.

For unstarted adaptive nodes, `fallback-to-coordinator` takes lifecycle input plus
`node_id`, `worker_created: false`, `reason`, `artifact_store`, and flags
`--dispatches`, `--journal`, `--current-capture`. Follow returned paths; other
dispatches/artifacts remain unchanged. Never rematerialize for one executor.
