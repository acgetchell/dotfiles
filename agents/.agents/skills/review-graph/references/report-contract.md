# Review Graph Reporting Contract

The proof store is exhaustive; the ordinary user report is compact. Do not
duplicate the routing ledger, node artifacts, lifecycle journal, and final proof
in conversation merely to demonstrate that they exist.

## Persisted Proof Store

Persist these records outside the reviewed repository:

- request, authorization, capture command, scope, and all three fingerprints
- compact routing overrides and planner-expanded exhaustive ledger
- graph plan, selected requirements, node identities, and dependencies
- worker attempts, execution locations, elapsed bounds, and blockers
- raw compact payloads, payload digests, compiled artifacts, and evidence
  envelopes
- independent-review native artifacts
- validation requirements, coalesced units, executions, reuse, and artifacts
- synthesis bundles, synthesis results, and predecessor mappings
- findings, changes, invalidation events, and replacement evidence
- artifact manifest, resume manifest when incomplete, and final
  `RepositoryReviewProof`

The persisted journal is the audit surface. Keep exact records and raw artifacts
unchanged; do not replace them with conversation summaries.

## Before Dispatch

Send one compact note containing:

- capture mode and bounded scope
- execution profile and authorization
- selected surface routers and focused skills
- number of review, validation, independent, and synthesis nodes
- artifact-store location

Do not print every `not-applicable` catalog entry or complete node dispatch.
For isolated-only failure before dispatch, report the capability blocker and
resume location, then stop.

## Default Final Report

Lead with findings and blockers. Include:

### Review Outcome

- `complete` or `incomplete` from the verified proof gate
- execution profile
- concise counts for selected and accepted review nodes, validation units,
  findings, changes, and blockers

### Findings

List every canonical actionable finding with severity, tight location, owner,
evidence, remediation, and final disposition. Include fixed findings. Mention
duplicates or withdrawals only when they clarify reconciliation.

### Changes

For review-and-fix work, state each material change, its finding or incidental
change ID, exact files, rationale, and validation. For review-only work, state
that no files were changed.

### Validation

List each unique command or canonical recipe once with requirement IDs and
result. Distinguish execution from exact reuse. Failed or blocked validation
remains evidence, not an automatically promoted finding.

### Coverage And Limitations

Name selected skills, explicit exclusions, blocked or stale requirements,
unresolved handoffs, untested configurations, and remaining risks. Omit routine
`not-applicable` candidates; their exhaustive records remain in the proof
store.

### Proof And Repository State

State the final branch and HEAD, index/worktree mutation status, final
repository-state fingerprint, proof status, verifier identity, artifact-manifest
identity, and proof-store location.

## Incomplete Results

When incomplete, inline only the exceptional resume data required to continue:

- blocked or unaccepted node IDs and exact skills
- outstanding validation or synthesis dependencies
- unresolved handoffs or stale evidence
- captured fingerprints and resume-manifest location
- whether a fresh root task is required

Do not inline completed node reports or unaffected routing records.

## Expanded Proof View

Render exhaustive lifecycle, skills-run, routing-disposition, validation,
evidence, compatibility, and repository-state tables only when the user asks for
the full proof or when debugging a verifier rejection. Derive every row from the
persisted accepted bundle rather than regenerating it from memory.

## Reconciliation

Before reporting `complete`, run `review_graph_runtime.py finalize-proof`. It
derives and verifies these equalities from the plan and persisted artifacts:

```text
selected nodes = accepted current nodes
planned validators = accepted validator evidence
review requirements = accepted review evidence or exact reuse
validation requirements = accepted validation evidence or exact reuse
canonical findings = fixed + remaining + accepted-risk + blocked
material changed files = union of compiled change records
```

Also require closed routing, resolved handoffs, current post-fix capture,
accepted synthesis, a verified artifact manifest, and an accepted
`RepositoryReviewProof`. Conversation output is never completion evidence.
