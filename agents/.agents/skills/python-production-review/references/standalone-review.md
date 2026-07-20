# Standalone Python Production Checklist

Load this reference only when `python-production-review` is invoked directly for a broad review. Skip sections that do not match the changed surface and route deep specialist concerns to their owning skills.

## Scope And Contracts

- Establish changed-code, branch, release, or whole-repository scope.
- Identify public modules, entry points, external consumers, persisted formats, and user-visible behavior.
- Separate correctness and compatibility blockers from optional cleanup.

## API And Type Design

- Check cohesive responsibilities, naming, parameters, return values, protocols, generics, overloads, and exported symbols.
- Verify annotations agree with runtime behavior and avoid `Any`, unjustified casts, and misleading optional values.
- Check subclassing and protocol contracts only where callers rely on them.
- Route invariant-bearing raw inputs and validated models to `python-parse-dont-validate`.

## State And Failure Behavior

- Trace construction, mutation, retries, cache updates, and multi-step operations.
- Verify failures do not publish partial state or destroy a prior valid result.
- Check idempotence where operations may be retried.
- Verify error categories and messages expose useful context without leaking secrets.

## Resources And Side Effects

- Trace ownership and cleanup of files, directories, subprocesses, sockets, database connections, temporary artifacts, locks, generators, and background tasks.
- Check early returns, exceptions, cancellation, and partial iteration.
- Flag import-time I/O, network calls, environment mutation, or process-global configuration.
- Verify writes are atomic when replacing important user or generated files.

## Async And Concurrency

- Check task ownership, structured shutdown, cancellation propagation, blocking work, shared-state protection, queues, backpressure, and worker failure reporting.
- Check thread/process-safe assumptions around caches, clients, random generators, and callbacks.
- Require deterministic tests for reachable races or cancellation-sensitive state.

## Security And Privacy

- Check shell commands, deserialization, dynamic imports, temporary files, path containment, archive extraction, permissions, and broad cleanup.
- Check logs, errors, fixtures, and diagnostic output for secrets or private records.
- Validate externally supplied environment, config, metadata, and paths before privileged effects.

## Packaging And Portability

- Route build artifacts, installation, package discovery, extras, entry points, and declared matrices to `python-build-portability`.
- Check runtime code for locale, timezone, encoding, path, case-sensitivity, and implementation assumptions.
- Distinguish tested configurations from declared support.

## Scientific, CLI, Notebook, And Tooling Surfaces

- Route numerical and mathematical validity to `python-scientific-review`.
- Route user-facing CLI behavior to `python-cli-review`.
- Route release, benchmark, fixture, and CI scripts to `python-support-scripts`.
- Route notebooks and their generated-output policy to `jupyter-notebook-review`.
- Route workflow mechanics and tool pins to `project-tooling-review`.

## Tests And Evidence

- Route test design to `python-test-quality`.
- Require regression evidence for corrected behavior, failure atomicity, public contracts, and configuration-sensitive branches.
- Apply the main skill's validation ledger, including source/environment state,
  built artifact and installation target, Python/platform/dependency
  configuration, instrumentation, and exact selection. Reuse matching evidence
  instead of replaying it through a broader command.
- Add only focused evidence absent from the ledger; rerun after invalidating
  changes or for an explicitly distinct configuration or nondeterminism probe.
- Record unavailable services, platforms, interpreters, or optional dependencies as limitations rather than implied passes.

## Final Synthesis

- Deduplicate findings from selected specialists.
- Lead with reachable correctness, data-loss, security, compatibility, or release blockers.
- State changed files, fixes, validation performed or reused, meaningful limitations, residual risks, and skipped specialists whose absence may otherwise look accidental.
- End with the main skill's `PASS`, `NEEDS IMPROVEMENT`, or `FAIL` verdict.
