---
name: javascript-parse-dont-validate
description: "Parse untrusted JavaScript or TypeScript inputs into validated domain values. Use for API JSON, configuration, forms, URL parameters, storage, and schema libraries such as Zod; not for ordinary component styling."
---

# JavaScript Parse Don't Validate

Identify untrusted entry points and establish runtime evidence before assigning
domain meaning. Use TypeScript for application code where the repository does,
but preserve JavaScript projects rather than forcing a migration.

## Boundary contract

Treat fetch JSON, JSON.parse, storage values, postMessage data, URL parameters,
and environment variables as unknown. A TypeScript interface, generic fetch type,
as-cast, non-null assertion, or satisfies expression cannot validate runtime data.

Use an existing schema library such as Zod when available, deriving static types
from the schema where useful. Use a small explicit parser for narrow boundaries
instead of adding a dependency by habit. With Zod, choose parse/safeParse and
input/output types intentionally, especially with transforms/defaults. Verify the
installed major version before copying schema APIs.

Define unknown-property, missing/null, coercion, and default behavior at the boundary.
Do not silently coerce malformed input into a legitimate zero, false, or empty list.
Return errors that callers can distinguish from successful empty results.

## Invariants and preservation

- Check finite numbers, integer/safe-integer ranges, counts, and arithmetic units.
  Number, parseInt, truthiness, and Date construction accept surprising inputs.
- Specify date/time-zone semantics and validate Invalid Date and ambiguous local
  times where they affect behavior.
- Parse closed categories with unions/enums and reject unknown values unless the
  API's compatibility policy deliberately preserves them.
- Validate URL scheme/origin and resource identity before using a link for
  navigation, credentials, or network requests. Encoding is not authorization.
- Use branded types only when construction is controlled and callers benefit from
  the distinction. Do not scatter unchecked casts to satisfy the brand.
- Keep trusted objects immutable where mutation could break the invariant;
  TypeScript readonly does not freeze an object at runtime.

Validate before cache insertion, state publication, external effects, or persistence.
Avoid reparsing the same trusted value in every component. Keep server authorization
authoritative even if forms or client schemas validate the same field.

## Evidence

Use the existing runner (often Vitest) for valid controls, malformed and missing
fields, boundary values, NaN/Infinity, coercion traps, and invalid combinations.
Test the public parser and consumers' handling of rejection; do not merely snapshot
a schema's internals. Use MSW for actual HTTP-to-parser behavior when relevant.
Run typechecking separately: static and runtime validation prove different things.
