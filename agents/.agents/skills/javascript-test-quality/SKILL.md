---
name: javascript-test-quality
description: "Design, write, or review JavaScript/TypeScript unit and UI integration tests using the repository's runner, commonly Vitest, Testing Library, and MSW. Covers async state, network errors, runtime parsing, and account isolation."
---

# JavaScript Test Quality

Choose the smallest test that can fail for the real user-visible defect. Inspect
the package manifest, runner config, environment, and existing helpers first.
Preserve Jest, Vitest, or node:test when already chosen; do not migrate frameworks
or add browser tooling without a demonstrated need.

## Unit and boundary tests

Test parsers, transformations, reducers, and pure domain decisions directly.
Include successful controls and materially different failures. Avoid copying the
implementation into the expected result or testing TypeScript casts as though they
were runtime validation.

Use the project's assertion library. Table-driven tests suit real input partitions;
large snapshots and coverage-only tests rarely prove a contract.

## React and HTTP integration

Use Testing Library queries by role/name and user-event for interactions.
Assert visible pending, empty, partial, stale, error, and reauthentication states.
Test components through the router/query providers they actually depend on.

Prefer MSW at the HTTP boundary for API behavior when installed. Treat unexpected
requests as failures. Mocking the query hook itself cannot prove query keys,
headers, cancellation, parsing, or transport error behavior.

Create an isolated QueryClient per test, choose retries deliberately, and clean up
handlers/subscriptions after each test. Exercise account switches and query changes
to detect data leakage and obsolete results. Do not mock authentication into success
when the test claims to verify access rejection.

## Async control

Await findBy queries, user interactions, and expected state transitions. Use waitFor
for retrying assertions, not to repeat side effects. Coordinate races with explicit
deferred promises or signals. Exercise reversed response order and cancellation
when affected.

Use fake timers only when time is part of the behavior. Integrate timer advancement
with user-event and React updates, then restore real timers. Avoid arbitrary sleeps
and universal flush-everything helpers that conceal unresolved promises.

Keep spies narrow, restore them, and assert the operation failed for the intended
reason. Do not globally silence errors that would reveal broken test setup.

## What needs a browser

jsdom does not prove layout, native navigation/downloads, browser cookie policies,
or real OAuth. Use the repository's browser framework, such as Playwright, for
those claims when available. Keep real-provider login/consent separate from routine
tests and never inject live credentials into fixtures.

## Validation report

Run relevant tests, typecheck/build, and configured lint. Separate deterministic
unit/UI evidence from browser and live-service acceptance. State unverified
behavior explicitly. Do not add tests for reversible cosmetic edits unless a
meaningful regression risk justifies them.
