# Review Profile Acceptance

Use this contract to decide which review profile may be selected by default.
Useful review delivery takes precedence over an unexecutable isolation plan.

## Grouped Delivery Gate

Keep grouped delivery as the default while it:

- selects every applicable tooling, C++, Rust, Python, and documentation
  orchestrator for the requested scope
- loads each selected orchestrator and its applicable focused skills
- preserves shared-file ownership and cross-surface handoffs
- returns findings or explicit no-finding outcomes for every selected surface
- accounts for validation without replaying equivalent checks
- records blockers without discarding completed surface evidence
- applies and revalidates fixes only when authorized
- produces the five-row `Review Evidence` compatibility table

A grouped review is incomplete when an applicable surface, required validator,
or unresolved handoff is silently omitted. It is still useful when a visible
blocker affects only part of the scope; report the partial evidence.

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
These deterministic tests prove the model, not runtime operability.

## Isolated Forward Gate

Do not make isolated execution the default until task artifacts contain three
consecutive accepted forward trials for each major mode:

- branch or pull-request read-only
- whole-repository baseline or release readiness
- review-and-fix

Also require one forced worker-creation failure with successful grouped fallback
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
execution explicit-only. It must never disable grouped review delivery.

## Compatibility Policy

Keep `repo-review` as the grouped default and repository routing authority.
Allow users to request `isolated` with transparent fallback or `isolated-only`
without fallback. Never describe grouped evidence as isolated, and never return
only isolated planning artifacts when grouped delivery remains authorized and
possible.
