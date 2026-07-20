---
name: python-production-review
description: "Review Python code for production readiness as a lean final synthesis after focused Python specialists or as a standalone broad review. Use for ordinary reusable modules, public APIs, exception and resource contracts, object lifecycle, import behavior, security-sensitive integration, async or concurrency risks, cross-cutting correctness, and release-readiness concerns not owned by CLI, parsing, scientific, support-script, notebook, packaging, or test specialists."
---

# Python Production Review

Perform a production-readiness review without repeating focused specialist passes. Use orchestrated mode for final residual synthesis and standalone mode when this skill is invoked directly for a broad Python review.

## Choose The Mode

### Orchestrated Mode

Use when `python-review-orchestrator` already selected and applied focused skills.

- Read only this file.
- Do not load the standalone checklist.
- Treat specialist findings and validation as established evidence.
- Inspect cross-cutting integration and concerns that remain genuinely unowned.
- Do not repeat parsing, CLI, scientific, notebook, support-tooling, packaging, or test checklists.

### Standalone Mode

Use when invoked directly for a broad production review or when no focused orchestrator ran.

- Read [`references/standalone-review.md`](references/standalone-review.md).
- Select only checklist sections that match the changed surface.
- Bring in focused skills when a concern requires their deeper workflow.

## Ownership Boundaries

Route primary ownership as follows:

- packaging, built artifacts, install behavior, runtime matrices, extras, and entry points: `python-build-portability`
- user-facing CLI and application behavior: `python-cli-review`
- invariant-bearing input parsing and domain models: `python-parse-dont-validate`
- mathematical and numerical validity: `python-scientific-review`
- development, release, benchmark, fixture, and CI scripts: `python-support-scripts`
- notebook structure and reproducibility: `jupyter-notebook-review`
- test design and durable evidence: `python-test-quality`
- workflow mechanics, validators, and tool versions: `project-tooling-review`

Retain final responsibility for integration among those surfaces and for ordinary reusable Python modules that match none of them.

## Residual Review

### Public And Cross-Module Contracts

Check that public functions, classes, protocols, and module exports have cohesive responsibilities, precise inputs and outputs, stable exception behavior, and no accidental exposure of implementation details. Verify that typing strengthens rather than disguises runtime behavior.

Flag unused generic constraints, ambiguous sentinel values, widening to `Any`, incompatible override behavior, or callers required to know undocumented sequencing rules.

### Correctness And State

Trace important operations from accepted input to committed result. Check coordinated mutation, cache/index coherence, idempotence, retries, partial failures, and observable post-error state. Prefer building a valid replacement before publishing it when multiple values must change together.

Use the parsing specialist for construction-time domain invariants; retain multi-component lifecycle and integration behavior here when no narrower state specialist applies.

### Exceptions And Diagnostics

Check that callers can distinguish actionable failure categories, exceptions preserve useful context and causal chains, cleanup does not hide the original failure, and normal user or data errors do not leak irrelevant implementation tracebacks.

Avoid broad exception swallowing, exception-driven control flow across large regions, and `assert` for runtime validation.

### Resource And Lifetime Contracts

Check files, sockets, subprocesses, temporary paths, database connections, locks, generators, iterators, context managers, callbacks, and background work for deterministic cleanup. Trace early returns, exceptions, cancellation, partial iteration, and interpreter shutdown where relevant.

Flag resources whose ownership is unclear, generators that defer required cleanup without a documented close path, callbacks retaining objects unexpectedly, and import-time acquisition of external resources.

### Async And Concurrency

When async, threads, processes, signals, or callbacks are present, check cancellation, task ownership, shutdown, blocking calls in async contexts, race-prone shared state, lock scope, queue backpressure, exception propagation, and deterministic testing. Recommend a dedicated specialist only when this surface grows enough to justify one.

### Security And Privacy

Check unsafe deserialization, shell construction, path traversal, broad deletion, temporary-file exposure, secret logging, private-record output, dynamic imports, and trust placed in environment variables or external metadata. Keep findings tied to reachable behavior rather than generic hardening advice.

### Integration And Simplification

Reconcile contracts across modules, installed entry points, generated artifacts, documentation examples, and external consumers. Look for duplicated adapters, obsolete compatibility layers, redundant wrappers, or abstractions that make invariants harder to see. Recommend deletion only when callers and validation evidence support it.

## Final Validation

Use the strongest focused evidence already produced. Add validation only for an integration path not covered by specialist checks. Do not run full CI solely because this is the final pass; follow repository requirements and escalate when changes span multiple layers without narrower coverage.

## Output

In orchestrated mode, synthesize specialist outcomes, remove duplicate findings, identify cross-cutting blockers, and name residual risk. In standalone mode, lead with findings ordered by severity and list focused skills or checklist sections used. Always report validation performed and meaningful limitations.
