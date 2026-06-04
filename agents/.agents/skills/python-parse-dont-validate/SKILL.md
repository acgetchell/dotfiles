---
name: python-parse-dont-validate
description: "Audit Python code for parse-don't-validate design, type-checkable invariants, boundary parsing, typed configuration/report models, dataclasses/attrs/Pydantic validation, Enum/Literal/NewType/refined wrappers, and mypy/pyright-friendly invalid-state prevention. Use for Python reviews asking whether raw dicts, strings, floats, counts, paths, subprocess output, JSON/CSV/TOML/YAML, CLI args, or optional fields should be parsed into validated domain types before computation. Do not use for general Python style, test quality, or scientific numerical correctness unless the issue is invariant storage or discarded validation evidence."
---

# Python Parse Don't Validate

Review Python code for boundary parsing and invalid-state prevention. Python
cannot make invalid states unrepresentable as strongly as Rust, so the goal is
to combine runtime validation at boundaries with as much static evidence as
Python's type system can carry inward.

## Scope Modes

Default changed-code mode:
- Audit changed Python code first.
- Inspect nearby unchanged constructors, parsers, dataclasses, config loaders,
  and compute functions only as needed to decide whether invalid state can be
  stored.

Pull-request mode:
- Use when the user says "PR", "pull request", "this branch", or "diff against
  main".
- Prioritize changed boundary parsing, public helper APIs, config/data models,
  and type-checkable invariants.

Whole-repo baseline mode:
- Use only when the user explicitly asks for a whole-repo or baseline audit.
- Review CLI/config loaders, JSON/CSV/TOML/YAML parsing, subprocess-output
  parsing, common dataclasses/models, and functions that accept `dict[str, Any]`
  or raw primitives with semantic constraints.

## Review Goals

### 1. Identify Invariants

Name the invariant before recommending a type. Common Python invariants include:

- value is finite, non-NaN, positive, nonzero, normalized, or within a range
- count is positive or bounded
- string is one of a fixed set
- path exists, is a file/directory, or is under an allowed root
- JSON/CSV/TOML/YAML shape has required fields and mutually consistent values
- subprocess output matches an expected schema
- optional value is present only in one domain state
- report/config dimensions or lengths agree

Do not force refined wrappers for passive report shapes with no meaningful
invariants.

### 2. Parse at Boundaries

Flag raw values that enter computation without a parse step:

- CLI args from argparse/click/typer
- environment variables
- JSON/CSV/TOML/YAML data
- subprocess stdout/stderr
- filesystem paths
- loosely typed external API responses
- public helper arguments that accept raw primitives with semantic constraints

Prefer a boundary shape plus fallible conversion into a validated domain object:

- raw `TypedDict`/plain dict only at the input boundary
- `@dataclass(frozen=True, slots=True)`, `attrs`, or Pydantic model for validated
  data
- `Enum` or `Literal` for finite categories
- `NewType` or a small wrapper class for semantically distinct strings/ints
- `Path` plus explicit validation for filesystem constraints
- parser functions named `parse_*`, `from_raw`, `try_*`, or `load_*` that raise a
  typed/domain-specific exception or return a result object according to local
  convention

Prefer stdlib `dataclasses`, `typing`, `Enum`, `Literal`, `NewType`, and
`TypedDict` unless `attrs` or Pydantic is already a project dependency or clearly
justified by existing validation needs.

### 3. Maximize Static Evidence

Use Python typing to preserve validation evidence where it helps reviewers and
type checkers.

Prefer:

- precise return types instead of `Any`
- `TypedDict` for raw JSON-like shapes before parsing
- `dataclass(frozen=True, slots=True)` for validated internal models
- `Enum` over enum-like strings in core logic
- `Literal[...]` for narrow public choices when an enum would be too heavy
- `NewType` for IDs or units that should not mix accidentally
- `Protocol` for structural dependencies instead of raw duck-typed objects
- `TypeGuard` or `TypeIs` only when a predicate truly narrows a type and the
  narrowed evidence is used immediately; with Python 3.13 available, prefer
  stdlib `typing.TypeIs` for exact narrowing predicates where it fits

Flag:

- `dict[str, Any]`, `Mapping[str, Any]`, or raw JSON values passed deep into
  computation
- `cast(...)` used to silence missing parsing
- `# type: ignore` hiding invalid input paths
- `Optional[T]` used when a small enum or variant-specific dataclass would encode
  the states better
- raw `str` modes repeatedly compared throughout core logic

### 4. Keep Validated Objects Valid

Prefer immutable validated objects. If mutation is needed, validate before
changing state.

Flag:

- setters that mutate then validate
- mutable dataclasses with invariant-bearing public fields and no validation
- `__post_init__` validation on mutable classes whose fields can later become
  invalid
- defaults that create placeholder invalid objects
- getters that raise because stored state may be invalid

Prefer:

- frozen dataclasses or attrs models
- replacement-style updates that construct a new validated object
- property setters that validate before assignment when mutation is necessary
- infallible accessors once construction has succeeded

### 5. Separate DTOs from Domain Models

Raw DTOs are fine at I/O boundaries and for passive reports. They are not the
type core algorithms should trust when fields have semantic constraints.

Accept:

- `TypedDict` or plain dict for raw parsed JSON
- flat report dataclasses that callers only inspect
- test fixtures that deliberately model invalid input before rejection

Flag:

- raw DTOs passed directly into computation
- report objects later reused as inputs to invariant-bearing APIs
- DTO fields whose mutually valid combinations are documented in comments rather
  than encoded in a validated domain model

### 6. Error Behavior

Boundary parsing should fail loudly and informatively.

Prefer:

- local typed exceptions for library/tooling boundaries
- `ValueError`/`TypeError` only when local convention is simple and callers do not
  need structured fields
- error messages that include observed values and expected constraints
- no partial mutation on failure

Avoid:

- returning `None` for invalid input when callers need the reason
- generic `Exception`
- letting `KeyError`, `TypeError`, or `AttributeError` leak from raw input parsing
  unless that is the documented local convention

### 7. Tests and Type Checking

Ask for tests when validation behavior changes.

Prefer tests that:

- cover every rejection reason
- assert the error type/message or structured fields
- cover NaN, infinities, empty strings, bad paths, missing keys, extra keys, and
  boundary counts when relevant
- verify failed mutation leaves the previous object unchanged
- exercise parser boundaries separately from computation

Prefer type-checker protection when feasible:

- avoid widening validated models back to raw dicts
- avoid `Any` in new code
- run the repo's configured checker (`mypy`, `pyright`, `basedpyright`, or local
  commands such as `just python-check`)
- recommend stricter annotations only when they catch realistic invalid-state
  regressions

## Output Format

### Scope
- State default changed-code, pull-request, or whole-repo baseline mode.

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Order by severity.
- Include file and line references.
- Explain the invalid state that can be stored or the validation evidence that
  is discarded.

### Suggested Fixes
- Say where parsing/validation should move.
- Name the model, enum, `NewType`, `TypedDict`, or wrapper that should carry the
  proof.
- Identify tests and type-checking commands needed.

### Optional Improvements
- Note refinements that improve clarity without blocking correctness.
