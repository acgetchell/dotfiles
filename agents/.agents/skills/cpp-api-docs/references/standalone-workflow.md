# Standalone C++ API Documentation Workflow

Read this reference only when `cpp-api-docs` is invoked directly without an
exact parent scope, validation ledger, and result contract. Documentation, C++
orchestrator, and review-graph dispatches already own this information.

## Scope Modes

Use changed public or cross-module documentation by default. Use
whole-repository mode only when explicitly requested.

## Validation

Prefer repository commands. Relevant focused evidence includes documentation
generation with warnings treated according to policy, link and navigation
checks, compilation and execution of canonical examples, minimal external
consumers for include or import claims, and supported compiler variants for
portability-sensitive documentation.

Record unavailable generators, platforms, or compilers as limitations rather
than implied passes.

## Standalone Report

Lead with misleading safety, lifetime, failure, concurrency, or portability
contracts. Then report missing public coverage, discoverability and rendering
failures, example problems, source-owner handoffs, validators run, and
remaining evidence gaps.
