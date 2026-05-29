---
name: rust-parse-dont-validate
description: "Audit Rust code for parse-don't-validate design, invariant-bearing types, smart constructors, fallible setters, infallible getters, private fields, and invalid-state prevention on changed code, whole repositories, or pull requests when requested. USE FOR: Rust reviews asking whether invalid values can be stored, whether constructors/builders/setters validate immediately, whether computations can become infallible after validation, whether public fields bypass invariants, whether refined newtypes should encode constraints, whether validation is delayed until use, whole-repo parse-don't-validate baseline audits, or PR audits focused on invariant boundaries. DO NOT USE FOR: general Rust style/import review (use rust-style-hygiene), generic test-quality review (use rust-test-quality), error enum design alone (use rust-error-variants), or non-Rust code."
---

# rust-parse-dont-validate

Audit Rust code for invalid-state prevention and parse-don't-validate design.

The goal is to reject bad input at the boundary, store only valid values, and let
later computation operate on invariant-bearing types without repeated defensive
checks.

## Scope

Depending on the requested scope, inspect Rust code that:

- introduces or changes structs, enums, builders, constructors, setters, parsers,
  deserialization, configuration, checkpoint loading, or public fields
- stores values with invariants such as counts, dimensions, indexes, probabilities,
  finite floats, normalized weights, ranges, paths, IDs, modes, topology, or
  algorithm parameters
- validates values after construction, immediately before use, or repeatedly in
  compute functions
- returns `Result` from computation only because earlier validation evidence was
  discarded
- accepts raw values where a refined type, newtype, enum, or `NonZero*` type could
  encode validity

Ignore passive report/DTO structs with no meaningful invariants unless public
fields can be fed back into invariant-bearing APIs.

DTO means data transfer object: a passive shape used to carry data across a
boundary, such as a wire format, config-file representation, API response, test
fixture, or report. DTOs are useful at boundaries, but they are not a substitute
for invariant-bearing domain types.

## Rust Idiom Guardrails

This skill should not push Java-style boilerplate into Rust code.

Prefer idiomatic Rust boundaries:

- prefer parsing into a more precise type over validating and returning `()`;
  if a check proves something, ask what type should carry that proof
- public fields are fine for passive data with no invariants
- private fields plus accessors are appropriate when fields carry invariants
- use `TryFrom`, `FromStr`, fallible constructors, or builder `build` methods for
  raw-to-refined conversion
- use `From` only when conversion cannot fail
- use `Option` for absence, not for explaining invalid input
- use `Result` when callers need to know why raw input was rejected
- keep getters and borrowed accessors infallible whenever stored data is already
  valid
- treat `*_unchecked` APIs as internal, unsafe-style escape hatches unless they
  are clearly documented and justified
- when standard traits such as `Extend` or `FromIterator` force infallible APIs,
  ensure fallible alternatives such as `try_extend` or `try_from_iter` exist when
  invalid input matters

### Scope Modes

Default changed-code mode:
- Use when the user asks for this skill without an explicit scope.
- Audit newly added or modified invariant-bearing code.
- Use nearby unchanged code only to understand local conventions.

Pull-request mode:
- Use when the user says "PR", "pull request", "this branch", "diff against
  main", or similar.
- Identify the PR/diff base from local repository context or the user's explicit
  target.
- Audit changed invariant-bearing APIs first, then any unchanged constructors,
  setters, deserialization paths, or compute functions needed to decide whether
  the changed code can store invalid state.
- Report findings against the changed code when possible. Mention unchanged
  supporting code only when it creates or preserves the risk.
- Keep the review PR-sized: prioritize merge-blocking invalid-state risks,
  public API hazards, and missing tests for new validation behavior.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline
  audit", or similar.
- Audit public constructors, builders, setters, deserialization boundaries,
  configuration/checkpoint types, and common validation helpers.
- Prioritize API boundaries and stored invalid states over cosmetic type
  refinements.
- Group related findings by type/module so the user can split follow-up work.
- Do not require fixing every historical issue in one patch; identify the highest
  leverage invariant boundaries first.

## Review Goals

### 1. Identify Invariants

For each changed type or API, name the invariants it relies on.

Examples:

- count must be positive
- probability must be finite and within `[0, 1]`
- log value may be `-inf` but not `NaN` or `+inf`
- index must be within a collection
- enum-like string must be one of a fixed set
- dimensions must agree
- checkpoint counters must be internally consistent

If no invariant exists, do not force smart constructors or private fields.

### 2. Validate Before Storage

Flag any path that stores raw invalidable values before validation.

Check:

- `new`, `try_new`, `from_*`, `parse`, `builder.build`, and setter methods
- `Default` implementations
- struct update syntax made possible by public fields
- direct derived `Deserialize` on invariant-bearing public or private fields
- internal constructors used by tests, examples, or deserialization
- mutation that partially updates an object before validation can fail

Prefer:

- fallible constructors/parsers for raw input
- private fields for invariant-bearing data
- validation before mutation, with atomic accept/reject behavior
- custom `Deserialize`, `TryFrom`, or builder `build` methods when raw serialized
  data can be invalid

### 2.5. Use DTOs Only at Boundaries

DTOs are appropriate for raw transport and passive reporting. They should not be
the type that core algorithms trust when fields have semantic constraints.

Prefer a two-layer design:

- raw DTOs with simple fields for deserialization, serialization, fixtures, or
  passive reports
- fallible conversion from raw DTOs into refined domain types
- domain types with private invariant-bearing fields and infallible accessors
- computation over the refined domain types, not over raw DTOs

Flag:

- raw deserialized/config DTOs passed directly into computation without a parse
  or `TryFrom` step
- report/passive DTOs later reused as inputs to invariant-bearing APIs
- DTOs with public fields whose values must be mutually consistent for methods
  to behave correctly
- "DTO" naming used to justify storing invalid algorithm state

Accept:

- public fields on passive reports/results that callers only inspect
- raw config/wire structs that are immediately parsed into validated types
- test fixtures that deliberately model invalid input before rejection

### 3. Make Invalid States Unrepresentable

Prefer encoding invariants in types when doing so reduces repeated validation or
clarifies API contracts.

Consider:

- `NonZeroUsize`, `NonZeroU64`, or other standard refined types
- small domain enums instead of finite string categories
- newtypes such as `PositiveWeight`, `FiniteLogProb`, `Probability`,
  `SampleCount`, `Dimension`, `ValidIndex`, or domain-specific IDs
- smart constructors with private fields
- accepting refined types in infallible APIs once validation has already happened

Do not introduce a new type if it only adds ceremony and the invariant is local,
obvious, and already impossible to violate.

For example, prefer a smart constructor that returns a refined value:

```rust
struct PositiveWeight(f64);

impl PositiveWeight {
    fn new(value: f64) -> Result<Self, WeightError> {
        if value.is_finite() && value > 0.0 {
            Ok(Self(value))
        } else {
            Err(WeightError::InvalidPositiveWeight { value })
        }
    }

    const fn get(self) -> f64 {
        self.0
    }
}
```

over a standalone `validate_positive_weight(value) -> Result<(), _>` whose
caller can ignore or forget the evidence it produced.

### 4. Keep Getters Infallible

Getters and borrowed accessors should normally be infallible views of already
valid stored data.

Flag:

- getters returning `Result` because stored data may be invalid
- getters that validate cached/raw fields before returning them
- accessors that panic on recoverable invalid stored state

Prefer:

- fallible construction or mutation
- infallible getters returning values, references, slices, or iterators
- fallible computation only when the computation itself can fail for a reason
  distinct from input validation

### 5. Use `Result` at Boundaries

Fallible constructors, parsers, builders, and raw-value setters should return
`Result<_, Error>` with an appropriate typed error.

Check that:

- each rejection reason maps to a useful error variant
- errors include relevant observed values and expected constraints
- generic `InvalidInput`, string errors, `anyhow`, or `Box<dyn Error>` do not hide
  caller-visible validation failures in library APIs
- setters that accept raw values validate before changing `self`
- constructors that accept already-refined types are infallible when no other
  failure is possible

Coordinate with `rust-error-variants` when error enum design needs deeper review.

### 6. Move Validation Out of Computation

Flag compute functions that revalidate object invariants every time they run.

Prefer:

- a single validation/parsing step at the boundary
- private unchecked helpers only reachable with validated values
- infallible computation over refined types
- documented internal debug assertions only for impossible invariant violations

Keep runtime checks when:

- the computation depends on dynamic external state that can change independently
- the invariant is too expensive to preserve eagerly and the API documents the
  trade-off
- the function accepts raw input directly and is itself the boundary

### 7. Tests

Validation behavior needs direct tests.

Prefer tests that:

- cover every rejection variant
- assert structured error fields, not only `is_err()`
- include boundary values and adversarial floats (`NaN`, infinities, signed zero
  when relevant, subnormal/tiny values, huge finite values)
- use adversarial property tests for broad numeric/count/input spaces when invalid
  values can be generated systematically
- verify failed setters/builders leave the original value unchanged
- verify downstream compute functions are infallible on accepted values

If a repository has a property-test placement convention, follow it.

### 8. Semgrep Guardrails

When a repo already uses Semgrep or similar project rules, consider adding
narrow guardrails for recurring parse-don't-validate regressions.

Good rule targets include:

- public `*_unchecked` APIs in production code
- infallible raw-value ingestion for known invariant-bearing types
- refined fields regressing from `NonZero*`, newtypes, or enums back to raw
  primitives
- public `validate_* -> Result<(), _>` APIs where a constructor/parser/newtype
  should carry the proof
- direct `Deserialize` derives on invariant-bearing domain types without a raw
  DTO plus fallible conversion step

Keep these rules repo-specific and low-noise. Semgrep should catch known bad
shapes and protect established invariants; it should not try to infer every Rust
invariant. If the repo has Semgrep fixtures, add positive and negative examples
for new rules.

## Common Findings

Flag these patterns:

- public invariant-bearing fields
- `new(...) -> Self` that accepts raw invalidable values
- `validate_*(&self)` required before normal use
- `is_valid` boolean APIs whose result is not encoded in the returned type
- delayed validation in `run`, `compute`, `sample`, `step`, or `finish`
- constructors that accept invalid values for later rejection
- setters that mutate first and validate later
- `Default` producing placeholder invalid values
- derived deserialization bypassing smart constructors
- getters returning `Result` because invalid data was stored

Accept these patterns when justified:

- public fields on passive reports with no invariants
- raw DTO structs used only at input/output boundaries and parsed into domain
  types before computation
- infallible constructors from refined types
- `unsafe` or unchecked internal constructors that are private, documented, and
  only called after validation
- lazy validation when preserving the invariant eagerly is measurably too
  expensive and the API explicitly owns that trade-off

## Output Format

### Scope
- State whether the audit used default changed-code mode, pull-request mode, or
  whole-repo baseline mode.

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Ordered by severity.
- Include file and line references.
- Explain the invalid state that can be stored or the validation evidence that is
  discarded.

### Suggested Fixes
- Say where validation should move.
- Name any refined type/newtype/error variant that should be introduced.
- Identify tests or property tests needed to lock the invariant down.

### Optional Improvements
- Note non-blocking refinements that would improve clarity without changing
  correctness.
