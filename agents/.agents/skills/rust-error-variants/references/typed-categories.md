# Typed Error Categories

Finite, caller-visible categories should be typed as enums instead of strings.
Treat string fields as display/detail payloads, not semantic schema. A string
field in an error is acceptable only when the value is genuinely unbounded or
opaque, no caller should branch on it, tests do not need exact string matching
for behavior, and no importer/exporter, retry path, diagnostics aggregator, or
compatibility check will parse it later.

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
