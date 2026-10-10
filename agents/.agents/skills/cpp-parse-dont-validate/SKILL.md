---
name: cpp-parse-dont-validate
description: "Design or audit C++ input boundaries and domain types so accepted values retain their invariants through construction and mutation."
---

# C++ Parse Don't Validate

Convert raw external representations into domain types that can represent only
supported states. Let core computation accept those types and rely on their
invariants instead of repeatedly checking raw values.

## Ground Rules

- Read repository-local instructions and follow the established C++ standard,
  compiler matrix, serialization stack, and error model.
- Name the invariant before introducing a wrapper or changing an API.
- Keep passive transport and report types simple when core behavior does not
  trust their fields.
- Do not promise more than a C++ type can prove. Account for aliasing, mutation,
  moves, lifetimes, contextual invariants, and unchecked internal paths.
- When asked only to explain or audit, remain read-only. When asked to implement,
  preserve compatibility unless the user authorizes an API break.

## Scope Modes

Use changed-code mode by default. Inspect changed invariant-bearing code and the
nearby constructors, parsers, mutators, and consumers needed to establish its
contract.

Use pull-request mode when the user names a PR, branch, or diff base. Prioritize
new public boundaries, invalid stored states, discarded validation evidence, and
missing rejection tests.

Use whole-repository baseline mode only when explicitly requested. Start with
public construction, configuration, deserialization, setters, and validation
helpers; group findings by owning type rather than proposing a repository-wide
wrapper rewrite.

## Workflow

### State the invariant and its owner

For each value or related field set, record:

- valid and invalid examples
- whether validity is lexical, numeric, relational, temporal, or contextual
- the object that owns the canonical invariant
- whether validity can change after construction
- whether callers need to distinguish rejection reasons

Typical invariants include positive counts, finite probabilities, checked
dimensions, compatible lengths, normalized weights, nonempty identifiers,
finite categories, valid mode-specific payloads, canonical paths, and mutually
consistent topology or configuration fields.

Do not create a refined type when no meaningful invariant exists or when the
value is only a passive output.

### Separate raw and domain representations

Keep raw data at external boundaries such as CLI arguments, wire formats,
configuration files, database rows, C APIs, and serialization libraries. Convert
it once into a validated domain type before core computation.

Prefer:

- raw DTO or serialization structs for transport
- a fallible parser, factory, or conversion that checks the complete contract
- a domain type with private invariant-bearing fields
- infallible observers and computation over the domain type

Public aggregate fields are acceptable for passive raw or report shapes. They
are not an adequate domain boundary when arbitrary aggregate initialization or
later assignment can violate behavior-critical invariants.

### Representation and construction

For new or changed domain constructors, factories, or conversions, read
[construction](references/construction.md).

### Keep valid objects valid

Check every mutation and exposure path:

- setters validate all dependent values before committing any change
- failed updates preserve the prior valid state
- mutable references, pointers, spans, iterators, and container access cannot
  bypass the invariant owner
- replacement-style operations construct valid state before swapping or
  assigning when that makes failure atomicity clearer
- caches and derived state cannot drift from canonical fields
- inheritance or slicing cannot bypass construction and mutation contracts

Prefer operations named for valid domain transitions over generic setters. Use
`cpp-invariant-state-transitions` for coordinated mutation and
`cpp-exception-safety-error-contracts` for rollback, exceptions, and `noexcept`
guarantees.

### Avoid false or stale proofs

Some facts cannot be carried safely by a detached value type:

- an index is valid only for a particular collection state
- an iterator, view, span, or string view is valid only while its source lives
  and remains suitably unmodified
- filesystem existence and permissions can change after checking
- a handle may be valid only for one owner, generation, transaction, or thread
- normalized or topology-valid data may become invalid through aliased mutation

Bind proof to the owner or generation when practical, keep the check and use
together when the world can change, or redesign the operation around an owner
method. Do not name a wrapper `Valid*` when its property can silently expire.

### Keep validation evidence inward

After conversion succeeds:

- accept the validated domain type in internal helpers
- return it from parsers rather than returning raw data plus `bool`
- keep accessors infallible for stored invariants
- avoid converting back to primitives until an actual external boundary needs
  them
- remove duplicated defensive checks only after every construction and mutation
  path preserves the proof

Keep invariant assertions for internal bug detection when useful, but never use
`assert` as the only rejection mechanism for reachable external input.

## Validation

Add focused tests for:

- the smallest and largest valid values and every meaningful rejection class
- negative-to-unsigned and narrowing boundaries
- NaN, infinities, signed zero, and numeric endpoints when relevant
- mutually dependent fields and variant-specific payloads
- default, copy, move, parse, deserialize, and round-trip behavior
- failed mutation leaving the previous object unchanged
- raw DTO rejection before core computation
- the absence of public creation or mutation paths that bypass the invariant

Run the repository's narrowest supported build and tests. Add compile-time checks
when constructor visibility, concepts, overload availability, or forbidden
implicit conversions are part of the contract. Use sanitizers when views,
aliases, or moved-from behavior make runtime lifetime evidence relevant.

For audits, order findings by the invalid state callers can create. Name the
invariant, bypass path, observable consequence, smallest boundary/type change,
compatibility cost, and regression evidence. Separate confirmed defects from
optional type-design improvements.
