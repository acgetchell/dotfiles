---
name: rust-invariant-state-transitions
description: "Audit Rust construction and mutation workflows for invariant preservation, coordinated state changes, failure atomicity, rollback, cache and index consistency, generation or provenance updates, and valid operation sequences. Use for fallible mutators, transactions and guards, topology or graph edits, state machines, builders that publish state, repair workflows, inverse operations, snapshot/restore logic, and mutations spanning canonical plus derived storage."
---

# Rust Invariant State Transitions

Audit whether every observable Rust value remains valid before, during, and after construction or mutation. Treat a transition as a contract over the complete owning state, not as a sequence of independently plausible field assignments.

## Ground Rules

- Read repository-local invariant, mutation, and validation guidance first.
- Default to changed transitions and the nearby canonical owner, derived state, callers, and tests needed to prove them.
- Keep raw-to-domain conversion under `rust-parse-dont-validate`, typed failure categories under `rust-error-variants`, and lifetime-bound views under `rust-borrowed-view-audit`. Route cancellation and synchronization whose correctness depends on `.await` or task boundaries to `rust-concurrency-async`; retain the underlying invariant and purely synchronous coordinated mutation here.
- Do not require a transaction abstraction when validation-before-commit or build-then-swap gives a simpler strong guarantee.
- Keep reviews read-only unless fixes are requested. Do not mutate git state without explicit authorization.

## Workflow

### 1. State the invariant and canonical owner

For each transition, record:

- the canonical storage and the type that owns it
- relationships among fields, collections, indexes, caches, handles, identities, generations, and telemetry
- valid initial, intermediate, committed, rejected, and moved-from states
- which properties are structural, numerical, temporal, owner-relative, or externally observable

Do not accept `is_valid()` as the invariant definition. Name the individual properties it proves and the state it inspects.

### 2. Enumerate every transition path

Inspect constructors, builders, setters, mutators, entry APIs, trait implementations, deserialization restore, repair, retry, commit, rollback, `Drop`, and internal unchecked helpers.

Trace:

- successful transition
- rejection before mutation
- failure after each mutation point
- early return, panic, callback failure, allocation failure, and destructor cleanup where reachable
- repeated, inverse, nested, or partially overlapping operations

Ensure ordinary public use cannot observe or persist an intermediate invalid state.

### 3. Make publication atomic

Prefer the smallest correct shape:

- validate all raw preconditions before mutation
- compute a complete replacement value, then assign or swap
- stage a delta and commit it once all fallible work succeeds
- mutate through one owner method that updates every coupled field
- use a scoped guard when rollback or deferred commit is genuinely required

Do not mutate one field and rely on later validation to repair related state. If only a basic guarantee is possible, document the exact post-failure state and prove it remains usable or safely destructible.

### 4. Audit rollback and transaction guards

When rollback is required, check that the guard begins at the highest owner of all affected state and restores canonical storage plus indexes, caches, hints, identities, counters, generations, and diagnostic state.

Check:

- `Drop` rolls back unless ownership was deliberately consumed by commit
- explicit commit, rollback, restore-and-retry, and nested use have unambiguous semantics
- fallback strategies restore the original state before attempting another path
- rollback snapshots preserve owner identity and handle provenance where ordinary `Clone` would not
- raw low-level primitives do not create redundant inner transactions beneath an owning transaction
- no view, iterator, key, or handle escapes with stale validity after restore or commit

Keep cancellation across `.await`, lock acquisition, and cross-task observation under `rust-concurrency-async`, while this skill owns the synchronous state guarantee being protected.

### 5. Keep derived state synchronized

For caches, adjacency, lookup tables, summaries, sorted keys, reverse maps, and generation counters, identify whether each value is canonical, derived eagerly, derived lazily, or invalidated explicitly.

Require one of:

- update every dependent value in the same commit
- invalidate it reliably and rebuild before observation
- derive it on demand from canonical state
- remove it when the consistency proof costs more than the cache saves

Treat cache invalidation and provenance as correctness, not only performance.

### 6. Verify sequences and inverse behavior

Review meaningful operation sequences, not only isolated calls. For graph, topology, simulation, workflow, and state-machine code, cover repeated application, rejected attempts, inverse operations, retry after failure, and transitions at boundary states.

When an inverse is promised, define what identity means: exact storage, canonical representation, public equality, topology, counts, or scientific equivalence. Do not accept recovered counts as proof of full restoration.

## Validation

Use the repository's narrowest supported tests first. Add evidence for:

- each successful and rejected transition
- failure injection after every meaningful mutation stage
- unchanged state after rejection or promised rollback
- cache, index, identity, generation, and handle consistency
- drop rollback, explicit rollback, commit, restore-and-retry, and nested transactions when present
- sequences, inverse operations, repeated mutations, and boundary states
- property or model-based tests when the transition space is combinatorial

Use snapshots only when they independently capture the full promised state. Prefer structural assertions and typed errors over a single production validity helper.

## Finding Standard

For each finding, name the invariant, canonical owner, transition and failure point, observable invalid state, smallest atomic correction, and focused regression evidence. Distinguish a confirmed corruption path from an optional architectural simplification.

## Handoff

Summarize transitions inspected, guarantees established, rollback or commit behavior, derived-state consistency, tests and validators, routed ownership/error/concurrency follow-up, files changed, and confirmation that no git state mutation occurred when true.
