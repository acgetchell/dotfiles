# Serialization and Restore Boundaries

Load this reference when Serde, configuration, wire formats, checkpoints, database rows, migrations, or persistence restore can create invariant-bearing Rust state.

## Separate Transport From Domain State

Prefer:

1. a raw serializable/deserializable DTO
2. fallible conversion into the domain type
3. computation over the accepted type
4. explicit conversion to an output DTO when persistence shape differs from the domain model

Do not derive `Deserialize` directly on private invariant-bearing fields unless custom deserialization or a validated helper proves the complete contract before publishing the value.

## Restore Complete State

Check:

- format version and migration ordering
- missing, defaulted, unknown, and duplicate fields
- numeric narrowing and non-finite behavior
- relational invariants across fields
- canonical versus derived/cache state
- owner identity, generation, handle provenance, and index rebuilds
- corrupted, truncated, incompatible, and future-version input

Restore canonical state first, validate it, then rebuild derived state. Do not trust persisted caches or indexes unless the format explicitly owns and validates them.

Use `rust-invariant-state-transitions` when restore publishes coordinated state or must be failure-atomic. Use `rust-error-variants` for version, corruption, migration, and invariant failures.

## Tests

Cover valid round trips, each rejection category, old-version migration, unknown/future versions, malformed and truncated input, malicious sizes, invalid dependent fields, and failure that leaves the prior in-memory state unchanged.
