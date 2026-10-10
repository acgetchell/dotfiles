---
name: csharp-parse-dont-validate
description: "Design or review C# runtime input boundaries so parsing, serialization, and mutation preserve domain invariants."
---

# C# Parse Don't Validate

Find the boundary where weak input becomes trusted. Use the smallest C#
representation that carries the actual invariant; do not create wrappers merely
to rename primitives.

## Raw and trusted representations

Use DTOs for transport shapes and explicit parsers/factories for domain values.
Keep invalid raw states representable in a DTO if needed to produce useful errors,
then reject them before side effects. Prefer a private constructor with a named
factory for compound invariants. Follow the project's Result/TryParse/exception
convention rather than introducing a new result library.

Nullable annotations, required members, init setters, records, DataAnnotations,
and the null-forgiving operator are not proof that untrusted runtime values satisfy
the domain. Check serializer/model-binder paths, not only normal constructors.

## Checks that change decisions

- Parse enum/string categories explicitly; reject unsupported numeric enum values
  when the boundary is closed. Define unknown-value behavior for evolving APIs.
- Distinguish absent, empty, malformed, and unavailable where callers care.
- Validate finite floating-point values, count bounds, checked arithmetic, date
  offsets, and inclusive/exclusive time boundaries.
- Parse identifiers, tenant keys, and URIs once. Restrict scheme/authority/path when
  they control credential delivery or resource access. Escaping is not authorization.
- Treat ClaimsPrincipal as trusted only after the configured authentication handler
  has validated it; a claim name or email suffix cannot prove identity.
- Respect ordinal/case-sensitive external IDs. Check database collation separately
  from in-memory string comparison.

## Preserve the invariant

Do not expose setters or mutable collections that invalidate a constructed value.
Remember that record with-expressions and ORM materialization can bypass intended
factory paths. EF configurations, migrations, unique indexes, and relational tests
must agree with the domain contract.

Keep raw HTTP query strings, Graph/OData links, and configuration values out of
core computations until their allowed use is established. Preserve opaque state
instead of parsing and reconstructing undocumented tokens.

## Errors and evidence

Reject before network calls, persistence, or partial mutation. Return controlled
diagnostics without credentials, private content, or arbitrary upstream errors.
Use System.Text.Json and the repository's ASP.NET validation facilities at the
boundary; add custom converters only when they make every construction path safer.

Test boundary values, malformed JSON/configuration, missing/null fields, invalid
combinations, and attempts to bypass factories through serialization or mutation.
Use the repository's test framework, usually xUnit for an existing xUnit project.
Test observable rejection and preserved state, not private implementation methods.
