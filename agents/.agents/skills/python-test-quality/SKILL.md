---
name: python-test-quality
description: "Review Python tests, pytest fixtures, properties, stateful scenarios, async or subprocess evidence, package and configuration matrices, and regression coverage for meaningful behavioral confidence. Use for pytest, Hypothesis, parametrization, tmp_path, monkeypatch, capsys, doctests, golden files, malformed inputs, failure atomicity, nondeterminism, and focused coverage gaps. Route Codecov report triage to codecov-test-gaps."
---

# Python Test Quality

Evaluate whether tests prove behavior and risk contracts rather than merely execute lines. Own test design and durable evidence; let domain specialists define the behavior that should be true.

## Scope And Boundaries

Review tests and fixtures in the supplied scope. When invoked directly without
an exact parent scope, validation ledger, and result contract, read
[`references/standalone-workflow.md`](references/standalone-workflow.md).
Review-graph and Python-orchestrator dispatches already own that information.

- Own pytest structure, fixtures, assertions, parametrization, properties, test determinism, regression evidence, and test-layer configuration here.
- Let CLI, parsing, scientific, support, notebook, build, and production specialists define their domain contracts.
- Select this skill when tests or fixtures changed, test/coverage review is requested, or weak evidence is itself a material risk. Running focused tests alone does not require this skill.

## Behavior-Driven Structure

Frame each test as a behavior scenario:

- **Given** a meaningful starting state and inputs
- **When** one observable action occurs
- **Then** outcomes, diagnostics, effects, and unchanged guarantees are explicit

Use descriptive scenario-style test names and clear arrange/act/assert structure. Add literal Given/When/Then comments only when they improve a complex test; do not require a BDD framework or ceremonial comments for simple cases.

Prefer one primary behavioral reason to fail. Test through stable public seams when practical, while allowing focused private-helper tests for otherwise unreachable parsing or transformation logic.

## Assertions

Assert complete relevant outcomes:

- returned values and domain state
- exception category and stable diagnostic fields or substrings
- stdout and stderr separately
- exit status
- emitted files, schemas, permissions, and ordering
- calls or effects at real integration boundaries
- state preserved after rejection or failure

Flag no-exception-only tests, truthiness where exact structure matters, broad `pytest.raises(Exception)`, snapshots that hide the contract, duplicated production logic in expected values, and mocks asserted instead of behavior.

## Boundary And Failure Scenarios

Cover normal, empty, minimal, duplicate, boundary, malformed, missing, extra, permission-like, timeout, and partial-failure cases as relevant. Verify rejected operations preserve prior valid state and do not publish partial files, cache entries, indexes, or external effects. Include retry-after-failure when operations are expected to be retryable.

For parser behavior, distinguish each actionable rejection category. For CLI behavior, assert output channels and exit status. For resources, exercise cleanup across exceptions, cancellation, and partial iteration where reachable.

## Properties And Stateful Testing

Use parametrization for a known finite matrix. Use Hypothesis when broad generated input, algebraic properties, parser variation, or operation sequences provide more confidence than enumerated examples.

Prefer invariants, round trips, metamorphic relations, model-based state machines, and independently derived oracles. Record minimized regression examples for important discovered failures. Constrain generators to meaningful domains and make assumptions visible.

Route scientific property selection and mathematical oracle validity to `python-scientific-review`.

## Determinism And Isolation

Control randomness, time, timezone, locale, environment, current directory, filesystem order, network, subprocesses, and services. Use explicit seeds or generator objects when exact replay matters. Avoid global random state and tests whose expected value comes from `now()`.

Use `tmp_path` for writes and `monkeypatch` at stable seams. Keep fixtures small and local. Prevent shared mutable fixture state, import-order dependence, hidden environment requirements, and tests that read user data or machine-specific paths.

## Async, Concurrency, And Subprocess Evidence

When relevant, test cancellation, timeout, shutdown, worker exceptions, backpressure, race-sensitive state, and cleanup. Avoid sleep-based synchronization when events, barriers, or deterministic fakes express the contract.

For subprocess code, distinguish command-not-found, timeout, nonzero exit, malformed output, and successful empty output. Assert the resulting diagnostic without leaking secrets.

## Packaging And Configuration Evidence

When build or install behavior is the contract, test built artifacts rather than only in-tree imports. Cover the minimal supported Python/platform/extra/configuration combinations that distinguish behavior, external entry points, package data, optional imports, and installed consumers.

Let `python-build-portability` choose the meaningful matrix. Own whether the resulting evidence is durable, specific, and maintainable.

## Coverage Triage

Use uncovered lines as prompts, not goals. Prioritize public behavior, error paths, parsers, state transitions, file/process effects, configuration branches, and historical bugs. Skip or justify exclusion of unreachable defensive code, impractical platform fallbacks, debug-only paths, and boilerplate dispatch.

Use `# pragma: no cover` or branch exclusions sparingly and with a reason. Route report-driven gap discovery to `codecov-test-gaps`.
