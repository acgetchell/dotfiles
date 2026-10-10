---
name: csharp-service-boundaries
description: "Implement or review ASP.NET service integrations involving identity, downstream calls, cancellation, pagination, or persistence."
---

# C# Service Boundaries

Trace one request from transport authentication through authorization, domain code,
persistence, and downstream calls. Preserve the repository's target framework,
dependency-injection conventions, and existing client libraries.

Apply the sections below only to contracts involved in the requested boundary.
Do not expand a persistence-only change into a full identity or paging audit.

## Identity and authority

- Separate browser session authentication from API bearer authentication and from
  downstream delegated consent. Specify the scheme on protected machine endpoints.
- Validate issuer, audience, signature, lifetime, and the required capability before
  using the principal. Bind durable identities using stable provider keys.
- Resolve the authorized resource server-side on every call. Do not let a request
  supply another account, tenant, raw downstream URL, or token-cache partition.
- Keep tokens out of cookies, browser bundles, tool output, and logs. A convenient
  profile claim or development persona is not authorization.
- Make local authentication explicitly Development-only and test that it cannot
  satisfy production/API policies.

## Failure and async contracts

Use distinct outcomes for successful empty data, incomplete traversal, stale data,
disconnection, reauthentication, throttling, and upstream failure. Translate SDK
exceptions at the boundary without returning their raw text.

Pass CancellationToken through every awaited operation. Preserve caller cancellation
rather than converting it into success. Use TimeProvider for deadlines/backoff tests.
Choose one retry owner; inspect SDK middleware before adding another retry layer.
Respect Retry-After, bound attempts and total duration, and never retry a mutation
without its operation-specific safety/idempotency contract.

For pagination, preserve opaque continuations and required headers. Bind any
client-visible cursor to the authorized owner and query. At an item limit, keep
the unconsumed page suffix or stop at a safe page boundary. Explain coverage and
freshness; live traversal is not automatically a snapshot.

## Lifetimes and persistence

Check DI lifetimes, disposal ownership, and whether an injected HttpClient is owned
by an SDK adapter. Do not capture scoped services in singleton tools or workers.

Commit related data and its checkpoint atomically. Use idempotent processing and
concurrency control where retries/restarts can repeat work. Tests of transactions,
collations, leases, or uniqueness need the appropriate database provider.

Keep migration generation separate from application startup and database mutation.
Review SQL and key/token storage before deploying or scaling. A local key ring or
in-memory cache is not evidence of multi-instance readiness.

## Verification and reporting

Test boundaries through real ASP.NET middleware and the client SDK's HTTP adapter,
using synthetic signed tokens and scripted responses. Unit-test domain decisions
separately. Run repository build/test commands and report which live interactions
remain unverified. Do not add deployment, tenant changes, or external writes to an
implementation task without the user's authorization.
