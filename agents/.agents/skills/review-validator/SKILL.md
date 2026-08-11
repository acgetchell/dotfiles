---
name: review-validator
description: "Plan and execute repository validation against a captured source state, either by discovering canonical repository commands for a branch, staged or worktree changes, a release, or a whole-repository request, or by executing an exact review-graph dispatch. Always show a standalone outcome and portable review-graph ledger evidence. Return reproducible, fingerprinted pass, fail, blocked, reused, or not-applicable evidence without reviewing code, diagnosing findings, applying fixes, or broadening scope."
---

# Review Validator

Plan and execute validation as one self-contained skill. When invoked directly,
discover the repository's authoritative validation surface and construct the
plan. When invoked by `review-graph`, execute its exact plan without re-planning.
In both modes, act as an evidence producer, not a code reviewer or fixer.

Read [references/result-contract.md](references/result-contract.md) before
planning or executing validation. Use its invocation, dispatch, and result
formats verbatim.

## Select The Invocation Mode

- Use `graph-dispatched` mode whenever the request identifies itself as a graph
  dispatch or comes from `review-graph`, whether or not its Validation Dispatch
  is complete. Require every field; return `blocked` for any omission instead of
  falling through to discovery, re-planning, or broader commands.
- Treat one graph dispatch as one already-coalesced validation unit. Verify its
  complete coalescing identity and requirement-to-evidence mapping. Do not split
  it into one execution per requirement when one command or canonical recipe
  satisfies all of them.
- Otherwise use `standalone` mode. Do not require the user to supply commands,
  fingerprints, configurations, requirement IDs, or a validation ledger.
  Discover them, build an internal Validation Dispatch, show the compact plan,
  and execute it without pausing for confirmation unless a command itself
  requires approval.
- A subagent launched by a standalone validator receives an exact internal
  dispatch with `invocation: standalone`. Execute that one unit without
  repeating discovery or launching another worker.
- Never create or require a separate validation-planner skill or worker.

## Deliver The Result

- In standalone mode, never end after planning, commentary, command output, or
  child-worker reports. Wait for every dispatched unit, perform the parent state
  check and reconciliation, and send one complete Validation Result as the final
  user-visible response even when the outcome is passed, reused, or not
  applicable.
- Lead the native result with the Outcome Summary from the result contract. Show
  the uppercase validation outcome and counts for passed, failed, blocked, and
  reused requirements and executions.
- State that P0, P1, P2, and P3 were `not evaluated (validation-only)`. Never
  print zero findings or assign severity merely because commands passed or
  failed; only a review skill can establish review findings.
- Include the Validation Ledger Export in every result. A standalone invocation
  does not automatically register evidence in another task or a future
  `review-graph`. The user or caller must provide the complete Validation Result
  or its persisted artifact to the graph.
- Treat the export as portable candidate evidence, not a transferable pass.
  `review-graph` must recapture state and dispatch a validator to verify exact
  command, source, environment, configuration, and selection identity before
  recording reuse.
- List every requirement satisfied by a coalesced execution or verified reuse.
  Preserve the dispatch's requirement-to-evidence mapping so one execution can
  satisfy several owners without losing attribution.

## Build A Standalone Plan

1. Resolve the Git repository root and read every applicable repository
   instruction file. Treat a bare validation request as branch scope. Honor an
   explicit branch or pull-request base, staged-only scope, changed-worktree
   scope, or whole-repository scope. Map release validation to branch scope when
   it names a base; use baseline scope for an explicit whole-repository or
   default-branch release gate.
2. Capture the source state with
   `<review-validator-dir>/../review-graph/scripts/capture_scope.py`. Use the
   repository's Python policy, normally:

   ```sh
   uv run python <capture-script> --repo <repo> --mode <mode> [--base <base>] [--path <path> ...]
   ```

   Retain that exact command as `state_verification_command`. The manifest
   supplies the repository root, scope paths, scope fingerprint, worktree
   fingerprint, and repository-state fingerprint.
3. When branch, staged, or worktree capture contains no paths, or discovery
   proves that no validation requirement applies to the captured paths, build a
   zero-requirement plan. Run the before-and-after state checks and return
   `not-applicable`; do not run an aggregate gate merely to manufacture a pass.
4. Inspect only the captured path inventory, applicable instructions, task-runner
   definitions, manifests, build presets, and continuous-integration
   configuration needed to route validation. Do not inspect implementation
   semantics or search for defects.
5. Classify candidate commands from their repository-owned definitions and
   instructions as source/Git non-mutating or mutating. Do not rely on recipe
   names alone. Validation may create only the approved ignored or external
   artifacts described below; reject fixers, in-place formatters, generators,
   dependency or lock updates, source rewrites, staging, commits, and equivalent
   mutations.
6. Discover non-mutating commands in this authority order:
   - explicit commands in applicable repository instructions;
   - repository-owned task-runner or documented validation recipes;
   - commands used by repository-owned CI for the same platform and scope;
   - standard commands implied by checked-in build or package configuration only
     when no higher authority exists.
7. Select the smallest authoritative non-mutating command set that covers the captured
   surfaces and their shared configuration boundaries. Prefer a documented
   aggregate gate over reconstructing its individual tools. Use the full
   documented gate for whole-repository or release validation and whenever
   repository policy or cross-layer changes require it. Record meaningful skips
   and do not silently replace an unavailable canonical command with a weaker
   substitute.
8. Convert the selection into stable requirement IDs, exact commands and working
   directories, complete relevant environment/configuration identity, expected
   evidence, mutation classification and basis, dependency policy, allowed
   artifacts, and bounded elapsed-time budgets. Coalesce compatible requirements
   by source state, canonical recipe or exact command, environment/toolchain,
   features, platform, artifact ownership, and mutation/locking compatibility.
   Record unit-to-requirement and requirement-to-evidence mappings. Record
   whether units are sequential or independently parallelizable. Use supplied
   ledger entries only when their complete identities match; otherwise set the
   ledger to `none`.
9. If applicable validation is required but no safe authoritative non-mutating
   command can be determined, construct a blocked
   internal dispatch that records every authority inspected and the exact
   missing command, configuration, platform, credential, or scope decision. Do
   not run a mutating command or invent a substitute merely to avoid `blocked`.

## Parallelize Independent Units

- In standalone mode, keep discovery, source capture, the internal dispatch, and
  final reconciliation in the parent. Use fresh subagents for independent
  validation units when parallel execution will materially reduce elapsed time.
  Do not delegate a single quick unit merely to create concurrency.
- Prove independence before fan-out: units must have no prerequisite edge,
  shared mutable build or install target, exclusive tool or service, fixed port,
  incompatible environment mutation, or repository instruction requiring
  serialization. Otherwise run them sequentially.
- Give each worker only its exact internal dispatch, applicable instruction
  paths, the validator skill path, source identities, and result contract. A
  worker must run its own before-and-after state checks, execute only its unit,
  return the native Validation Result, and must not review, fix, re-plan, or
  delegate.
- Bound concurrency by available worker slots and repository or tool limits.
  If subagents are unavailable, execute the same plan locally; lack of fan-out is
  not a validation blocker.
- Accept worker evidence only when its fingerprints and complete execution
  identity match the internal dispatch. The parent independently rechecks state
  after all workers, preserves each native status and execution record, and
  computes the final status using the normal precedence rules.
- In graph-dispatched mode, remain a leaf worker. Do not spawn subagents; the
  graph already creates one validator node per independent validation unit.
- Serialization does not authorize source- or Git-mutating commands. Route those
  to sequential `review-graph` fix nodes, which must recapture source identity
  after each mutation; never execute them as validator units.

## Execute The Plan

- Verify every dispatch field and ensure commands are bounded to the repository,
  configuration, and requested scope. Independently reject a command whose
  repository definition is mutating even if a dispatch labels it non-mutating.
- Run the state-verification command before validation. Stop as `blocked` if any
  fingerprint differs from the dispatch or cannot be recorded.
- Reuse evidence only when command, source state, built artifact or installation
  target, environment, configuration, instrumentation, and exact selection all
  match.
- Execute a coalesced canonical command once and apply its accepted evidence to
  every mapped requirement. Do not replay it for each owner. Keep distinct
  platform, feature, packaging/consumer, artifact, or locking units separate.
- Execute each validation unit in its declared order. A unit may contain an
  ordered setup, build, and test sequence only when all commands share one
  configuration and evidence identity. Run separate units concurrently only
  under the independence rules above. Stop dependent commands after a
  prerequisite failure; continue independent units only when the dispatch
  permits it.
- Preserve exact commands, exit codes, concise output evidence, environment
  identity, elapsed time, and limitations. Do not report a pass from configured
  jobs, expected output, compilation flags, or a command that did not run.
- Run the state-verification command again. If scoped source, repository source,
  index, HEAD, or branch state changed, mark executions stale and return
  `blocked`. Report explicitly allowed ignored artifacts without treating them
  as source changes.
- Return the exact Validation Result format. Use `blocked` when a requirement
  could not execute or source identity was lost; otherwise use `failed` when an
  execution failed, `passed` when all requirements are satisfied and at least
  one command executed, and `reused` only when every requirement was satisfied
  without execution. Use `not-applicable` only when the plan contains zero
  requirements and zero commands because the captured scope is empty or no
  validation applies. In standalone mode, send that reconciled parent result to
  the user; do not leave it only in subagent output or scratch storage.

## Boundaries

- Do not load a review skill, inspect the change for defects, assign severity,
  diagnose failed evidence, synthesize findings, recommend fixes, or edit
  source-controlled files. Spawn only the bounded standalone execution workers
  permitted above.
- Do not mutate Git state. Permit build products, caches, coverage data, and logs
  only in repository-approved ignored locations or an explicit external artifact
  directory, and report them.
- Do not install a substitute toolchain, alter dependencies, or change
  configuration to make a command pass. Report unavailable tools, permissions,
  services, credentials, or platforms as blocked evidence.
- Treat a failed command as validation evidence, not automatically as a product
  finding. Leave diagnosis and ownership to `review-graph`, `review-agent`, or a
  focused reviewer.

`review-graph` still owns cross-node selection, deduplication, invalidation,
retries, and routing. `review-agent` independently reviews a concrete change.
This skill owns both planning and execution only for its standalone validation
request.
