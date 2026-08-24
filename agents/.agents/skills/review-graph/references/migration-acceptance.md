# Review Profile Acceptance

Use this contract to decide which review profile may be selected by default.
Useful review delivery takes precedence over an unexecutable isolation plan.

## Adaptive Delivery Gate

Keep adaptive grouped execution as the default while it:

- produces exhaustive repository and surface routing for the requested scope
- executes every selected leaf skill in a worker when possible or the
  coordinator when necessary
- preserves shared-file ownership and cross-surface handoffs
- returns accepted `ReviewEvidence` or an explicit blocker for every selected
  requirement
- dispatches validation through `review-validator` without replaying equivalent
  checks
- records blockers without discarding completed surface evidence
- applies and revalidates fixes only when authorized
- verifies `RepositoryReviewProof` and derives the five-row compatibility table
- dispatches every worker with no inherited turns and compiles compact review
  and validation payloads through the trusted runtime
- gives synthesis only the canonical hashed `SynthesisBundle`, while preserving
  complete predecessor artifacts in the proof store
- derives dispatches, synthesis records, requirement mappings, manifests, and
  the final proof from accepted planner/compiler artifacts rather than model
  transcription
- derives ready dispatches from a plan-bound, source-bound, digest-chained
  lifecycle journal whose accepted events reference verified artifacts
- keeps ordinary worker context within checked prompt budgets while retaining
  full provenance in the proof store
- publishes versioned planning/review/validation schemas and aggregates boundary
  diagnostics without coordinator field normalization
- compiles every planned mode, including conclusion-blind independent review,
  through an artifact-backed journal path
- prevents validator-command duplication, verifies workspace effects, and
  safely shares only read-only observations between semantic leaves
- recaptures before readiness and finalization; mutation epochs end in a fresh
  plan or terminal `awaiting-replan`, never stale redispatch

An adaptive review is incomplete when an applicable requirement, required
validator, or unresolved handoff is silently omitted. It is still useful when a
visible blocker affects only part of the scope; report the partial evidence.

## Isolated Deterministic Gate

Require on every isolated-planner change:

- every routing catalog skill resolves to one approved path whose frontmatter
  name matches the catalog skill ID
- every consulted router returns one disposition per catalog entry
- every selected leaf appears in the required graph or exact verified reuse
- no applicable skill is completion-satisfied by a budget skip
- every epoch preserves the worker reserve and complete node order
- late handoffs and post-fix rerouting close before synthesis
- baseline validation, applicable synthesis, and independent review are
  accepted where required
- fingerprints, node lifecycle equalities, and final report equalities reconcile

Run routing, planner, completion, failure/resume, and scope-capture tests in CI.
Also test artifact tampering; separate ordinary, validator, and complete
all-surface prompt budgets; and recursive exclusion of coordinator ledgers,
reports, proofs, and maintainer specifications from worker dispatches. These
deterministic tests prove the model, not runtime operability.

For leaf progressive-disclosure audits, rank candidates from actual selection
traces combined with loaded words. Keep domain reasoning in the entrypoint;
move only conditionally relevant standalone, fix, release, validation, or
reporting procedures, and add entrypoint budgets for the optimized leaves.

## Isolated Forward Gate

Do not make isolated execution the default until task artifacts contain three
consecutive accepted forward trials for each major mode:

- branch or pull-request read-only
- whole-repository baseline or release readiness
- review-and-fix

Also require one forced worker-creation failure with successful adaptive fallback
and one isolated graph continued across multiple fresh-root epochs.

Each trial must demonstrate:

- 100% applicable-skill recall against an independently adjudicated routing
  ledger
- zero silent omissions or unexplained extra owners
- every canonical actionable finding preserved
- every selected node accepted or explicitly incomplete
- complete validation, synthesis, fingerprint, lifecycle, and report evidence
- actual worker creation and reports from the supported runtime
- a recorded independent verifier identity and accepted verification result for
  the runtime artifact

Planner tests may construct fixtures to exercise this gate's logic, but those
fixtures are not forward-trial artifacts and cannot promote the isolated
profile outside the test process.

A failing isolated trial resets its consecutive count and keeps isolated
execution explicit-only. It must never disable adaptive review delivery.

## Compatibility Policy

Keep `review-graph` as the sole mixed-surface coordinator and repository routing
authority. Keep `repo-review` as a compatibility entrypoint that delegates to
it. Allow users to request `isolated` with transparent adaptive fallback or
`isolated-only` without fallback. Never describe adaptive evidence as isolated,
and never return only isolated planning artifacts when adaptive delivery remains
authorized and possible.
