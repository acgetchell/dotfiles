---
name: csharp-test-quality
description: "Design, write, or review C# unit and integration tests for .NET services, ASP.NET authentication, SDK HTTP clients, and EF Core persistence. Follow the repository's xUnit, NUnit, or MSTest setup instead of migrating frameworks."
---

# C# Test Quality

Map each requirement to an observable failure mode and the lowest test layer that
can prove it. Inspect the target framework, test SDK, assertion packages, and
existing tests before choosing tools. Do not silently migrate xUnit major versions
or add another runner.

## Use the right layer

- Unit tests: domain parsing, authorization decisions, state transitions, limits,
  and error mapping through small explicit collaborators.
- ASP.NET tests: use TestHost or WebApplicationFactory to exercise authentication
  schemes, middleware ordering, authorization policies, routing, and HTTP results.
  Directly calling a controller does not prove its Authorize attribute works.
- SDK integration: keep the real SDK/request adapter and script HttpMessageHandler
  responses to check actual URLs, headers, pagination, retries, and cancellation.
- Persistence: use relational tests for uniqueness, transactions, rollback, SQL
  behavior, and restart. SQLite may test portable relations; use the target engine
  for collation, provider SQL, concurrency, migrations, and locking claims.
  EF InMemory is not relational evidence.

## Async and lifecycle

Use async Task tests and await every assertion/operation. Follow the installed
xUnit version's fixture/IAsyncLifetime interfaces; v2 and v3 differ. Give each
test owned resources and deterministic disposal. Avoid shared mutable fixtures
when tests can run concurrently.

Use TimeProvider/FakeTimeProvider or explicit completion signals for time-dependent
behavior. Test cancellation during real await boundaries and distinguish caller
cancellation from an internal deadline. Never wait arbitrary seconds to make a
race appear resolved.

Inspect DI overrides: remove registrations when necessary so validation does not
construct superseded production dependencies. Keep live credentials and network
access out of ordinary test fixtures.

## Assertions that earn their cost

Use existing assertions (xUnit Assert or the installed assertion library).
Check results and relevant absence of side effects. For identity boundaries,
exercise a valid control case plus bad issuer/audience/signature/expiry/scope,
foreign resource identity, and actual browser-vs-API scheme separation.

For paging/retry work include empty intermediate pages, later-page failure,
mid-page limits, opaque cursor tampering, Retry-After, exhausted retries, and
restart/cancellation as applicable. Do not let a mocked method bypass the behavior
being claimed. For partial results, assert both retained evidence and incomplete
coverage.

Prefer theory cases for true input partitions. Avoid snapshots of incidental
formatting, tests that duplicate the algorithm, and assertions that only match
source code. A meaningful regression test should fail for the original bug.

## Validation report

Run the relevant project tests and required repository checks. Report actual
counts, failures, skipped tests, and external checks still needed. Separate unit,
synthetic integration, real-provider, and live acceptance evidence. Inspect
generated migration SQL before any database application.
