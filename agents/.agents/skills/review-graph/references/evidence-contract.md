# Repository Review Evidence Contract

This is a maintainer-facing verifier specification. Runtime review agents use
`runtime-contract.md`; the compiler and planner enforce this schema without
requiring workers to read or reproduce it.

Use this contract for every `review-graph` profile. Execution location may
change, but coverage, result identity, acceptance, and final reconciliation may
not. The stable schema version is `1`; `scripts/review_graph_plan.py` is the
deterministic verifier.

## Evidence Invariants

- Capture one source state before routing. Every concurrent read-only node uses
  that scope, worktree, and repository-state fingerprint tuple.
- Persist complete native results outside conversation context. A summary or
  parent-agent recollection is not reusable evidence.
- Hash the dispatched skill and every loaded reference. Skill names and paths
  without content digests do not establish execution identity.
- Record whether execution occurred in a worker or the coordinator. Adaptive
  execution accepts either; isolated execution requires a fresh worker.
- Keep review evidence, validation evidence, and final synthesis distinct. A
  validator does not produce review findings, and synthesis does not repair
  missing predecessor evidence.
- Reuse evidence only after recapturing source state and verifying the complete
  identity. Mark mismatches stale rather than overwriting them.
- Treat exact review reuse as typed non-executable evidence. Preserve the
  router's exact requirement-to-evidence mapping; do not create a leaf or
  independent-review node for reused work.
- Treat `fix` and `revalidation` results as transition history, never as final
  accepted proof evidence. After every fix, persist both reports in the
  invalidation history, recapture all three fingerprints, reroute, and build a
  new final-state plan containing only audit, independent-review, validation,
  and synthesis nodes plus exact non-executable reuse.

## Review Evidence

Create one `ReviewEvidence` envelope for each selected leaf, independent review,
fix, revalidation, or synthesis result:

```text
schema_version: 1
evidence_id: stable unique ID
node_id: exact graph node
requirement_ids: every requirement coalesced into this node
skill_id, mode: audit | synthesis | fix | revalidation | independent-review
skill_path, skill_digest
reference_digests: exact path and digest for every loaded reference
fingerprints: expected, observed before, observed after
execution_profile: grouped | isolated | isolated-only | mixed
execution_location: worker | coordinator
worker_created, fresh_context: exact booleans
status: completed | no-findings | blocked
finding_ids, validation_requirement_ids, handoff_ids
predecessor_evidence_ids: exact accepted predecessor evidence for synthesis,
  otherwise empty
raw_result_artifact_id, raw_result_digest
report_complete, source_mutated, git_mutated: exact booleans
```

For `independent-review`, the planner-derived `ReviewEvidenceExpectation` also
carries the exact concrete change target and ordered normalized inspected-path
tuple from the trusted routing dispatch, plus the maximum addressable line for
each inspected path as independently recaptured from the exact repository root,
capture mode, base ref, pathspecs, and source identities before planning. These
are trusted-capture expectation provenance, not caller- or worker-authored
claims. The native and bundle gates
accept a path-only repository-level location, but reject any positive line or
line range whose endpoint exceeds its trusted per-path bound.

The native result format remains in `node-contract.md`. The coordinator stores
that complete result, computes its artifact digest, creates the envelope, and
runs `assess_review_evidence`. `completed` and `no-findings` evidence satisfies
requirements only when identity, fingerprints, skill/reference digests, report
structure, and mutation rules match. A conforming `blocked` result is preserved
but does not satisfy its requirements.

## Validation Evidence

Every validation requirement maps to exactly one coalesced
`review-validator` unit. Persist its complete native Validation Result and
create one `ValidationEvidence` envelope:

```text
schema_version: 1
evidence_id, node_id, requirement_ids
skill_digest, reference_digests
fingerprints: expected, observed before, observed after
execution_profile: grouped | isolated | isolated-only | mixed
execution_location: worker | coordinator
worker_created, fresh_context: exact booleans
status: passed | failed | blocked | reused | not-applicable
command_identity_digest, environment_digest
raw_result_artifact_id, raw_result_digest
source_mutated, git_mutated: exact booleans
```

Derive `command_identity_digest` canonically from the exact coalesced
`ValidationUnit` commands, corresponding working directories, and canonical
recipe. Derive `environment_digest` canonically from that same unit's
environment, toolchain, features, platform, artifact owner, and mutation lock.
Construct the dispatch expectation with `validation_evidence_expectation`,
which computes both digests from the unit; neither digest is an opaque caller
assertion. Accept the result only when both envelope values equal those
independently derived expectations exactly.

The validation expectation also carries the exact dispatched validator skill
path and typed approved artifacts `(path, kind, repository_status)`. Reparse the
native Skill Loading, Reused Evidence, Artifacts, and Validation Ledger Export
sections and reconcile them exactly with that expectation and envelope. An
artifact must be an approved `ignored` or `outside-repository` path; a graph
result's ledger consumer is exactly `review-graph`, and every ledger identity,
digest, state, provenance, and handoff field must equal the accepted evidence.

Run `assess_validation_evidence` before importing the result into the graph.
Only `passed` and exact `reused` evidence satisfy nonempty requirements.
Accepted failed or blocked evidence remains visible for diagnosis and does not
become a review finding by itself.

## Native Result Evidence Block

Every persisted Review Node Result, repository independent-review result, and
Validation Result contains exactly one `## Machine Evidence` section ending in
one canonical block. The opening marker, one-line JSON object, and closing
marker are exact; do not use YAML or frontmatter:

```text
<!-- review-graph-evidence-v1
{"after_repository_state_fingerprint":"<digest>","after_scope_fingerprint":"<digest>","after_worktree_fingerprint":"<digest>","artifact_id":"<artifact-id>","before_repository_state_fingerprint":"<digest>","before_scope_fingerprint":"<digest>","before_worktree_fingerprint":"<digest>","evidence_id":"<evidence-id>","finding_ids":[],"git_mutated":false,"mode":"<audit|independent-review|synthesis|fix|revalidation>","node_id":"<node-id>","predecessor_evidence_ids":[],"repository_state_fingerprint":"<digest>","requirement_ids":[],"result_type":"<review-node-result|independent-review-result>","schema_version":1,"scope_fingerprint":"<digest>","skill_id":"<skill-id>","source_mutated":false,"status":"<completed|no-findings|blocked>","validation_requirement_ids":[],"worktree_fingerprint":"<digest>"}
-->
```

Validation results use the same markers and common identity fields, replacing
the review-only arrays with the exact validation dispatch identities:

```text
<!-- review-graph-evidence-v1
{"after_repository_state_fingerprint":"<digest>","after_scope_fingerprint":"<digest>","after_worktree_fingerprint":"<digest>","artifact_id":"<artifact-id>","before_repository_state_fingerprint":"<digest>","before_scope_fingerprint":"<digest>","before_worktree_fingerprint":"<digest>","command_identity_digest":"<digest>","environment_digest":"<digest>","evidence_id":"<evidence-id>","git_mutated":false,"mode":"validation","node_id":"<node-id>","repository_state_fingerprint":"<digest>","requirement_ids":[],"result_type":"validation-result","schema_version":1,"scope_fingerprint":"<digest>","skill_id":"review-validator","source_mutated":false,"status":"<passed|failed|blocked|reused|not-applicable>","validation_status":"<same-status>","worktree_fingerprint":"<digest>"}
-->
```

Serialize the JSON with sorted keys, no insignificant whitespace, and ASCII
escaping. The verifier accepts at most 1 MiB of UTF-8 Markdown, a 64 KiB block,
1,024 values per identifier array, and 4,096 characters per string. It rejects
missing, duplicate, truncated, non-object, non-canonical, unknown-field, or
wrong-version blocks before trusting their contents.

An `independent-review-result` adds exactly these sorted-key fields to the
review block: `"change_target":"<exact dispatch target>"`,
`"handoff_ids":[]`, and `"inspected_paths":[]`. Ordinary review result modes
must not add them.

The artifact gate requires the exact top heading and every required section
heading from `node-contract.md` or the validator result contract. For an
ordinary Review Node Result or Validation Result, it also parses the bounded
ordered header between the top heading and first section, requires every
mode-specific field exactly once with no extra prose, and binds every value to
the trusted dispatch or typed evidence. It compares the parsed block with the
typed expectation and envelope for artifact, evidence, node, skill, mode,
status, requirements, findings, validation status,
all expected/before/after fingerprints, and source/Git mutation. For an
ordinary review, it also requires Skill Loading to equal the exact dispatched
skill path/digest and ordered static-reference path/digest pairs. For a
validation result, it requires Validation Plan to be the complete canonical
typed dispatch/coalescing record and Requirements to equal every exact
requirement disposition and execution or reuse evidence identity. For an
independent result, it additionally requires the machine block and exact human
Scope Inspected/Review Graph Envelope fields to match the trusted change target
and ordered planned paths, reconciles both human Result dispositions with the
typed fingerprints and accepted status, and requires human routing handoffs to
equal the machine/envelope `ReviewEvidence.handoff_ids`. Accepted independent
results must state exact `none` limitations; blocked results must state one
concrete limitation. For synthesis,
it also derives predecessor evidence IDs from the proof's planner-owned node
mapping, adds final exact-reuse evidence where applicable, and requires the
expectation, envelope, and native payload to match exactly. The compatibility
`report_complete` Boolean is not completeness evidence at this gate.

## Repository Review Proof

After all routing handoffs close and final synthesis returns accepted review
evidence, construct one `RepositoryReviewProof`:

```text
schema_version: 1
proof_id, plan_digest, source_state
planned_node_evidence: planned executable node ID -> accepted evidence ID
required_review_requirement_ids
review_requirement_evidence: requirement ID -> accepted review evidence ID
exact_reused_review_evidence: reused requirement ID -> routed evidence ID
accepted_review_evidence_ids
required_validation_requirement_ids
validation_requirement_evidence: requirement ID -> accepted validation evidence ID
accepted_validation_evidence_ids
stale_evidence_ids, unresolved_handoff_ids
final_synthesis_evidence_id
artifact_manifest_id, artifact_manifest_digest
verifier_id
```

First call `repository_review_proof_expectation` with the accepted `GraphPlan`
and captured source state. It derives the canonical plan digest, exact required
review and validation IDs, their planned node mappings, and the exact
`repository-production-review` synthesis identity. Both
`assess_repository_review_proof` and `assess_evidence_bundle` require this typed
expectation and reject proof omissions, substitutions, or evidence produced by
an unplanned node. The expectation preserves every planned review node's exact
skill digest and ordered reference digests, and every validator's same
provenance plus the canonical identity of its complete coalesced
`ValidationUnit`. Bundle acceptance compares both the typed record expectation
and envelope to these plan-owned identities; internally consistent caller
rebinding cannot replace planned provenance or validator dispatch. The final
proof maps every planned final-state audit,
independent review, surface or repository synthesis, and validation node
exactly once. Fix and revalidation transition records remain in invalidation
history and make a final proof expectation fail closed if smuggled into the
recaptured plan. The only accepted review evidence without a planned executable
node is an exact evidence ID declared by the routing ledger and preserved
unchanged in the plan, expectation, and proof. Its envelope must match the
routed requirement, skill, path, mode, static references, and source state
through the normal review-evidence gate. Independent planned and exact-reuse
identities additionally retain the exact trusted change target and ordered
planned paths. A synthesis record is accepted only
after every planned predecessor and declared exact-reuse record have accepted
mapped evidence, and its native payload names those exact predecessor evidence
IDs.

Use the planner's canonical typed artifact structures:

```text
ArtifactManifestEntry:
  evidence_id, artifact_id, artifact_digest, entry_digest
ArtifactManifest:
  schema_version, manifest_id, verifier_id, entries, manifest_digest
ArtifactPayload:
  artifact_id, content: bytes
TrustedArtifactVerifier:
  verifier_id, digest_algorithm: sha256, artifacts: ArtifactPayload[]
```

Build each entry's artifact digest from the persisted raw-result bytes and its
entry digest from canonical `evidence_id`, `artifact_id`, and artifact-digest
data. Compute the canonical manifest digest from its schema version, manifest
ID, verifier ID, and sorted complete entries; exclude `manifest_digest` itself
so the digest definition is not self-referential.

`assess_repository_review_proof` validates the proof's internal mappings. Then
run `assess_evidence_bundle` with every evidence object the proof claims as
accepted, the typed `ArtifactManifest`, and a `TrustedArtifactVerifier` supplied
by the trusted orchestration boundary. The bundle gate re-runs the review and
validation verifiers; recomputes payload, entry, and manifest digests from the
trusted bytes; requires each envelope's raw artifact identity and digest to
match its manifest entry; parses the native Markdown headings and canonical
evidence block; and requires exact coverage between accepted evidence IDs,
manifest entries, and trusted payloads. Reject missing, extra, malformed,
truncated, semantically mismatched, stale, tampered, or self-asserted accepted
IDs. The proof's `unresolved_handoff_ids` must equal the globally unique ordered
concatenation of handoff IDs carried by all accepted review evidence. A
nonempty tuple remains completion-blocking; close and reroute each handoff, then
replace the affected accepted evidence with a newly verified result that
carries no unresolved handoff before constructing the final proof. Derive the user-facing findings,
validation ledger, five-row compatibility table, and repository-state report
only from the accepted bundle.

The completion gate receives the exact planner-derived expectation and proof,
the complete review and validation record sets, the typed artifact manifest,
and the trusted verifier payload boundary. It calls `assess_evidence_bundle`
itself; callers cannot submit an `EvidenceBundleAssessment` or success Boolean.
Only after that internal verification succeeds may completion derive review,
validation, synthesis, independent-review, and exact-reuse coverage from the
bound proof. Caller coverage fields are consistency assertions only and cannot
narrow the required graph.

## Parallel Execution And Barriers

Dispatch independent read-only review nodes concurrently when workers are
available. Give each worker only its exact dispatch and captured source state.
When adaptive execution cannot create a worker, execute that same node in the
coordinator and produce the same evidence envelope. Do not silently drop it.

Use these barriers:

1. Complete repository and surface routing before review dispatch.
2. Join independent review results, verify their evidence, and resolve late
   handoffs before validation or synthesis that depends on them.
3. Coalesce and execute validation requirements through `review-validator`.
4. Run surface and repository synthesis only from accepted predecessor evidence.

Fix nodes are always serialized. After a fix, persist the fix and revalidation
reports as the prior epoch's invalidation history, recapture source state,
reroute changed surfaces, and create a fresh final-state plan. Do not carry a
fix or revalidation executable node into that plan or its accepted bundle;
rerun only invalidated or newly required final-state audit,
independent-review, validation, and synthesis nodes.

## Persistence And Resumption

Persist the artifact manifest, native results, envelopes, routing ledger,
validation mappings, and invalidation history in session-owned storage or a
unique external artifact directory. Record its exact location in the final
report and resume manifest.

A future agent may reuse an ancestor's evidence only after verifying the
artifact manifest, schema version, result digests, skill/reference digests,
dispatch identity, and current source fingerprints. Conversation ancestry is
not evidence.
