---
name: cpp-scientific-correctness
description: "Audit C++ numerical, geometric, combinatorial, stochastic, and scientific code for mathematical validity, numerical robustness, reproducibility, and independently testable claims. Use when changes affect formulas, predicates, tolerances, topology, random sampling, Monte Carlo behavior, scientific fixtures, or research-facing results."
---

# C++ Scientific Correctness Review

Review scientific C++ by establishing the intended model first, then checking that the implementation computes that model across ordinary, boundary, and degenerate inputs. Treat passing tests as evidence only when their oracle is independent of the production implementation.

## Ground Rules

- Do not mutate git state unless the user explicitly asks in the current turn.
- Honor repository-local instructions, the documented scientific scope, and primary references.
- Verify current library or algorithm claims from authoritative sources when they are unstable or uncertain.
- Preserve scientific behavior unless fixing a verified defect. Do not bundle cosmetic modernization or broad architecture changes into a correctness fix.
- Establish correctness before discussing performance.

## Audit Workflow

### 1. Establish the scientific contract

Record the affected operation's:

- mathematical definition and supported domain
- units, coordinate conventions, orientation, sign, indexing, and normalization
- exact versus approximate guarantees
- expected invariants, conservation laws, and state deltas
- cited algorithm, paper, or authoritative library contract

Make hidden assumptions visible. If source and documentation disagree, treat that mismatch as a finding rather than choosing silently.

### 2. Check numerical behavior

Inspect:

- cancellation, overflow, underflow, loss of significance, and narrowing
- tolerance meaning and scale dependence; avoid unexplained magic epsilon checks
- NaN, infinity, signed zero, empty inputs, and degenerate geometry
- exact-predicate/inexact-construction boundaries and unsafe conversions
- iteration termination, conditioning, convergence, and fallback behavior
- arithmetic reordering that changes reproducibility or accepted error bounds

Use exact arithmetic or robust library predicates when the contract requires them; do not demand exactness where the documented model is approximate.

### 3. Check geometry, combinatorics, and topology

When applicable, verify:

- orientation and incidence conventions
- reciprocal adjacency and manifold conditions
- simplex, cell, edge, face, or vertex classifications
- exact count deltas and Euler-like consistency checks
- boundary and degeneracy handling
- use of public library primitives rather than undocumented representation assumptions

Combine this pass with `cpp-invariant-state-transitions` when scientific validity depends on coordinated mutation.

### 4. Check stochastic behavior

For random algorithms and simulations, verify:

- RNG ownership is explicit, normally at simulation or run level
- algorithms accept RNG state by reference instead of constructing, globally hiding, or implicitly reseeding engines
- tests and benchmarks can own deterministic, replayable RNG instances
- distributions remain conceptually separate from the engine
- selection and shuffling are unbiased for the intended domain
- proposal probabilities, acceptance ratios, and detailed-balance reasoning include asymmetric choices where needed
- counters distinguish proposed, applicable, accepted, rejected, and failed operations consistently

Preserve the repository's chosen default engine unless implementation evidence identifies a concrete reason to change it.

### 5. Demand independent evidence

Prefer a combination of:

- analytically known values and hand-checked minimal examples
- an independent implementation or trusted external oracle
- metamorphic properties, invariants, inverse operations, and round trips
- adversarial boundary and degeneracy cases
- seeded property or randomized stress tests with failing seeds reported

Do not use the same production helper as both implementation and oracle. Benchmark fixtures must be scientifically valid before their timing has meaning.

### 6. Validate and report

Run repository-owned targeted tests first, then the narrowest relevant sanitizer or numerical validator. If scientific behavior changes, rerun every affected known-value, property, and reproducibility test even when compilation is already clean.

For each finding, state the violated contract, input regime, observed or derivable error, authoritative basis, minimal fix, and independent regression evidence.

## Handoff

Summarize scientific contracts reviewed, changed files, fixed defects, independent oracles used, seeds or fixtures relevant to reproduction, validator results, residual limits, and confirmation that no git state mutations were performed when true.
