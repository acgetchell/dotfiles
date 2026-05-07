---
name: rust-error-variants
description: "Audit Rust error enums and error pathways for correctness, debuggability, and orthogonality on changed code or whole-repo baseline audits when explicitly requested. USE FOR: Rust review comments asking whether appropriate Error variants were added/used, error enum design, thiserror/Display messages, anyhow/Result mapping, preserving typed errors, adding missing variants, replacing generic validation errors, checking error pathway correctness, ensuring variants are mutually exclusive and actionable. DO NOT USE FOR: general Rust style/naming review (use rust-style-hygiene), test/doctest coverage review (use rust-test-quality), non-Rust code, or unrelated unchanged code unless a baseline audit is requested."
---

# rust-error-variants

Audit Rust error variants and error pathways for correctness, debuggability, and orthogonality.

Correct error design is part of correctness: callers need to distinguish failure modes, developers need useful messages, and tests should be able to pattern-match meaningful variants instead of parsing strings.

## Scope

Focus on newly added or modified Rust code that:

- introduces or changes error enums
- adds validation or fallible construction paths
- maps backend/library errors into domain errors
- changes `Result` return types or `?` propagation
- adds `thiserror`, `Display`, `From`, `map_err`, or `anyhow` usage
- returns generic errors such as `ValidationFailed`, `InvalidInput`, or string-only errors
- stores finite, caller-visible categories in `String`, `&str`, or `&'static str`
  fields instead of enums, especially fields named `kind`, `reason`, `level`,
  `check`, `operation`, `format`, `target`, `mode`, `type`, `source`, or
  subsystem-specific category names
- uses `Box<dyn std::error::Error>`, `Box<dyn Error>`, or `anyhow::Error`
  in production code, public doctests, examples, or benchmarks where a typed crate
  error would preserve caller-visible failure modes
- uses `&dyn Error` outside `std::error::Error::source`, standard-error trait
  verification tests, or lint fixtures intentionally exercising generic-error patterns

Ignore unrelated unchanged code unless needed to understand existing error conventions.

### Scope Modes

Default mode:
- Audit newly added or modified error types, fallible paths, and error conversions.
- Ignore unrelated unchanged errors unless they define the convention the changed code should follow.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit public error types, fallible public APIs, validation paths, backend/library error mappings, and common internal error conversion boundaries.
- Prioritize findings by caller-visible ambiguity, lost typed context, misleading variants, missing `#[non_exhaustive]`, and tests that cannot assert structured errors.
- Do not require fixing every historical error-design issue in one pass; separate API-breaking fixes from internal cleanup.

## Review goals

### 1. Correct variant selection

Check that each failure path uses the most specific existing error variant available.

Flag:

- generic catch-all variants used where a typed variant exists
- misleading variants that describe the wrong subsystem or invariant
- `map_err(|e| Error::Other(e.to_string()))` when callers need typed context
- conversion that loses useful fields from an underlying error
- generic `Box<dyn std::error::Error>`, `Box<dyn Error>`, or `anyhow::Error`
  return types in user-facing Rust examples, doctests, benchmarks, or public APIs
  when the crate has, or should add, a typed error variant
- `&dyn Error` outside legitimate `std::error::Error::source` implementations,
  tests that verify the trait behavior, or lint fixtures

Prefer:

- domain-specific variants with structured fields
- preserving typed errors where callers may pattern-match
- wrapping only when the wrapper adds meaningful context

### 2. Missing variants

Add a new error variant when a distinct invariant or failure mode cannot be represented accurately by existing variants.

Good reasons to add a variant:

- callers may want to handle the failure differently
- the condition points to a different corrective action
- the error message needs different structured context
- using an existing variant would be semantically false
- tests currently need to match strings because there is no typed representation

Avoid adding variants when:

- the distinction is cosmetic only
- the existing variant is intentionally broad and already has precise structured fields
- the new variant would duplicate another variant with different wording

### 3. Orthogonality

Error variants should be mutually understandable and not overlap confusingly.

Check:

- each variant represents one concept
- similarly named variants differ in a clear, documented way
- validation, construction, backend, and causality/topology/semantic errors are separated when those categories matter
- variant fields are minimal but sufficient to debug

Flag:

- multiple variants that could both apply to the same failure without a clear priority
- variants whose names imply one invariant but whose fields/messages describe another
- broad variants that become dumping grounds for unrelated failures

### 3.5. Enum-able categories

Finite, caller-visible categories should be typed as enums instead of strings.

Flag string fields when:

- the value comes from a fixed or nearly fixed set of literals
- tests compare the field to a string literal
- callers may branch on the value
- the field identifies a validation check, invariant level, resume reason,
  output/checkpoint operation, topology, move type, mode, format, or subsystem
- a typed enum already exists for the concept and the error stores `format!("{x:?}")`
  or `x.to_string()` instead

Prefer:

- small enums with `Display` implementations that preserve user-facing wording
- reusing existing domain enums such as topology, move type, output format, or
  validation level
- `#[non_exhaustive]` on public category enums when downstream exhaustive
  matching would be semver-hostile
- tests that pattern-match enum values instead of comparing strings

Leave string fields alone when:

- the value is genuinely open-ended context such as a path, identifier, handle,
  lower-level diagnostic, or free-form detail
- the value names a private helper operation used only for debugging and callers
  should not branch on it
- enum variants would mirror unbounded upstream errors without adding useful
  structure

### 4. Debuggable messages

Messages should explain what failed, the observed value, the expected condition, and relevant context.

Good messages include:

- the invariant/check name
- observed vs expected values
- relevant IDs, indices, labels, dimensions, counts, or ranges
- enough context to reproduce or locate the bad object

Flag:

- messages that only say "invalid" or "failed"
- messages that omit the offending value
- messages that expose secrets
- messages that contradict the variant name
- messages that force callers to parse text to recover structured information

### 5. Error propagation and conversion

Review `From`, `map_err`, and `?` paths.

Check that:

- `From<SubError>` mappings preserve the important context
- wrapping errors adds useful higher-level context without hiding typed variants unnecessarily
- public APIs return stable error types appropriate for callers
- internal helper errors are converted at module boundaries consistently
- `anyhow`/string errors are not used in library APIs where typed errors are expected
- public examples and doctests use the crate's typed result alias where available,
  mapping lower-level I/O, parser, serialization, and backend errors into narrow
  variants instead of returning `Box<dyn Error>`

When a `Box<dyn Error>` pattern appears:

- Identify each concrete `?` source hidden behind the boxed return.
- Reuse an existing typed variant only when its name and fields accurately describe
  that failure mode.
- Add a new variant when the hidden source represents a distinct output, checkpoint,
  parsing, backend, validation, or construction failure.
- Add or update tests that pattern-match the variant or assert its structured fields
  when the path is in production code.
- Leave `&dyn Error` alone in legitimate `std::error::Error::source`
  implementations, tests that explicitly verify `std::error::Error` behavior, or
  lint fixtures whose purpose is to exercise the generic error pattern.

### 6. `#[non_exhaustive]` for forward compatibility

Public error enums and their variants benefit from `#[non_exhaustive]` so adding variants or fields later is not a breaking change.

Check that:

- public error enums are `#[non_exhaustive]` unless there is a reason to lock the surface
- variants with public fields are `#[non_exhaustive]` when future fields are likely
- removing `#[non_exhaustive]` is treated as a breaking change
- internal error enums consumed only inside the crate are not marked `#[non_exhaustive]` for no reason; the attribute is most useful at the public API boundary

Flag:

- public error enums without `#[non_exhaustive]` that are likely to gain variants
- mixing exhaustive and non-exhaustive errors inconsistently across the public API
- callers (or doctests) that pattern-match on `#[non_exhaustive]` errors without a fallback arm

### 7. Tests

When error behavior changes, tests should validate typed behavior.

Prefer tests that:

- pattern-match the exact variant
- assert structured fields
- assert key Display text only for user-facing clarity
- cover each new distinct failure path

Avoid tests that only check `is_err()` for logic that depends on variant correctness.

## Output Format

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Concrete issues with file/function references
- For each issue, state the current error path and the better variant/path

### Required Fixes
- New variants to add, if any
- Existing variants to use instead
- Conversion or `map_err` changes needed
- Display/debug message improvements
- Tests to add or update

### Optional Improvements
- Non-blocking naming, field, or message refinements
