---
name: rust-borrowed-view-audit
description: Audit Rust APIs for opportunities to replace owned snapshots, caches, handles, and cloned topology with lifetime-bound borrowed views over canonical storage. Use when reviewing Rust libraries for stale-cache prevention, snapshot/view API design, transaction/rollback guard design, generation or identity checks, or performance/correctness tradeoffs around cloning versus borrowing.
---

# Rust Borrowed View Audit

## Purpose

Review Rust APIs for places where ownership, borrowing, and lifetimes can encode
correctness invariants directly. Prefer borrowed views when they prevent stale
use, cross-owner confusion, or mutation during observation without adding
runtime bookkeeping. Prefer mutable owner borrows or transaction guards for
topology mutation windows so Rust enforces mutable versus immutable access and
prevents mutating through stale detached identifiers.

This skill owns lifetime, aliasing, canonical-owner, snapshot/view, handle-provenance, and guard-shape questions. Route complete state publication, rollback contents, cache/index coordination, and operation-sequence atomicity to `rust-invariant-state-transitions`.

## Workflow

1. Identify the canonical owner of each relation or data structure.
   - Name the structure that is allowed to mutate the data.
   - Treat all other structures as views, derived indexes, detached snapshots,
     or rollback state.
   - If there is no clear canonical owner, call that out first.

2. Classify each candidate API.
   - **Borrowed view**: should borrow canonical storage and be lifetime-bound
     to it.
   - **Owned snapshot**: should own data because it must outlive the source,
     cross threads independently, persist, or support detached analysis.
   - **Derived index**: may own derived maps but should borrow canonical
     relations when possible.
   - **Rollback state**: may own a clone or delta, but should usually be hidden
     behind a guard borrowing `&mut` canonical storage.
   - **Mutable transaction/guard**: should hold `&mut` canonical storage for a
     scoped mutation or rollback window.
   - **Handle/key**: may remain copyable, but must carry enough provenance or be
     validated at use boundaries.

3. Look for parse-don't-validate smells.
   - Raw `HashMap`/`Vec` fields mutated from multiple modules.
   - `clone()` used mainly to dodge lifetimes rather than to create a true
     snapshot.
   - Runtime generation checks used where a borrow could prevent stale use at
     compile time.
   - Mutating algorithms carrying detached handles across phases when a scoped
     `&mut Owner` or transaction guard could prove owner existence and aliasing.
   - Public or crate-wide setters that can create impossible intermediate states.
   - Tests reaching through storage internals instead of using narrow
     invariant-specific test hooks.

4. Recommend the narrowest lifetime change that encodes the invariant.
   - Convert owned cache fields to `&'a CanonicalIndex` when the view should not
     outlive the owner.
   - Keep owned maps only for derived data not already stored canonically.
   - For query helpers that accept a derived index or cache, make the owner
     lifetime explicit in the function signature, e.g. `&'tds Owner` with
     `&AdjacencyIndex<'tds>`. If the returned iterator borrows only the derived
     index, use a separate `'idx` lifetime for the index borrow while preserving
     the index's `'tds` tie to canonical storage.
   - For mutating topology algorithms, make the mutation entry point take
     `&mut Owner` directly or use `Transaction<'a>`/guard types borrowing
     `&'a mut Owner` to prevent observation of intermediate mutation.
   - Within mutable guards, use short lexical scopes for borrowed views during
     read-only classification and validation, then drop those views before
     mutating.
   - Treat handles/keys inside mutation guards as short-lived, validated commit
     identifiers, not as proof by themselves that topology still exists.
   - Keep generation/identity checks for detached handles, cross-owner inputs,
     serialization boundaries, or manually constructed test fixtures.

5. Check mutation boundaries.
   - Ensure mutators validate or parse before storing invalid state.
   - Prefer relation-specific methods such as `insert_simplex`,
     `remove_isolated_vertex`, or `rebuild_from_storage` over exposing raw
     collection operations.
   - Make fallible mutators return typed errors when an invariant would be violated.
   - Verify mutation APIs do not accept detached handles as the primary
     authority when they could instead borrow the canonical owner mutably and
     validate inside that scope.
   - Verify rollback paths cannot leak partially mutated state through existing
     views.

6. Validate performance claims carefully.
   - Borrowing should remove avoidable clones or allocations, but do not assume
     it is faster without checking.
   - Account for any added preflight checks on hot paths.
   - For scientific or topology-heavy crates, prioritize correctness and
     invariant clarity before micro-optimizing.

## Review Output

Start with findings, ordered by correctness impact. For each finding include:

- The canonical owner and the accidental duplicate or stale view risk.
- The proposed borrowed-view or transaction-guard shape.
- Whether query/helper signatures explicitly tie returned views, iterators, or
  caches to the lifetime of the canonical data structure they consult.
- Whether mutating APIs hold a mutable owner borrow for the mutation window and
  keep borrowed views scoped before mutation.
- Whether runtime generation/provenance checks remain necessary.
- Any API break and why it improves correctness, performance, or orthogonality.
- Focused tests or compile-fail examples that would prove the lifetime invariant.

If no change is needed, say whether the API is a true owned snapshot, detached
handle, or rollback state and why borrowing would be worse.
