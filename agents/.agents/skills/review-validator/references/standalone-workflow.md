# Standalone Validation Workflow

Use this workflow only for a direct validation request. The validator owns
discovery, planning, execution, optional worker placement, reconciliation, and
the final user-visible result.

## Capture And Discover

1. Resolve the Git repository root and read applicable repository instructions.
   A bare request means branch scope. Honor explicit branch or pull-request
   base, staged-only, changed-worktree, whole-repository, path, and release
   scopes.
2. Capture source state with
   `<review-validator-dir>/../review-graph/scripts/capture_scope.py` under the
   repository's Python policy. Retain the exact capture command, repository
   root, captured paths, and scope, worktree, and repository-state
   fingerprints.
3. Inspect only captured path inventory, task-runner definitions, manifests,
   build presets, CI configuration, and instructions needed to route
   validation. Do not inspect code for defects.
4. Classify commands from repository-owned definitions. Reject fixers,
   in-place formatters, generators, dependency or lock updates, source
   rewrites, staging, commits, and equivalent mutations.
5. Choose commands in this authority order: explicit repository instructions;
   repository-owned documented recipes; repository CI for the same platform
   and scope; checked-in standard configuration only when no higher authority
   exists.
6. Select the smallest authoritative non-mutating set covering the captured
   surfaces and shared configuration. Prefer the documented aggregate gate for
   whole-repository or release validation. Record meaningful skips; never
   silently substitute a weaker command.

## Plan

Build stable requirement IDs, exact commands and working directories, complete
relevant environment and toolchain identity, expected evidence, mutation
classification, dependency policy, approved artifacts, and elapsed bounds.
Identify the actual executor platform and runtime separately from any target
platform. Classify target-bound evidence as native execution, focused emulation,
or unexecuted; emulation is a distinct configuration and cannot satisfy a
native requirement. Encode target platform and mode in the digest-covered
environment or features before coalescing.
Coalesce only requirements with identical source state, recipe or commands,
working directories, environment, toolchain, features, platform, artifact
ownership, and mutation lock. Preserve unit-to-requirement and
requirement-to-evidence mappings.

If the captured scope is empty or no validation applies, build a zero-unit plan
and return `not-applicable` after before-and-after state checks. If validation
is applicable but no safe authoritative command exists, return `blocked` with
the inspected authorities and exact missing prerequisite.

Show the compact plan and execute without pausing unless a command needs
approval.

## Execute

Verify every field and run the source-state command before execution. Execute
each coalesced command once and map its accepted evidence to every owned
requirement. Stop dependent commands after prerequisite failure; continue only
independent units when the plan permits it. Preserve exact commands, exit codes,
concise output facts, environment identity, elapsed time, approved artifacts,
and limitations. Include the actual host, native or emulated evidence mode, the
modeled boundary, and every unexecuted target cell. If supplied native CI
evidence for the same source state conflicts with local or emulated evidence,
preserve the native failure instead of reporting the matrix as passed.

Run the source-state check again. Any scoped source, repository source, index,
HEAD, or branch mutation makes the evidence stale and the result `blocked`.

## Optional Parallel Units

Keep capture, discovery, planning, and final reconciliation in the parent. Use
fresh workers only when independent units materially reduce elapsed time. Prove
they share no prerequisite, mutable target, exclusive tool or service, fixed
port, incompatible environment change, or serialization requirement.

Give each worker only its unit, applicable instructions, source identities,
validator skill path, and standalone result contract. Use no inherited turns.
The worker runs its own state checks, does not delegate, and returns its native
unit result. If workers are unavailable, run locally; this is not a blocker.

The parent independently rechecks state, verifies exact execution identities,
preserves each status and execution record, and reconciles the final result.

## Deliver

Always return the complete `Validation Result` from `result-contract.md`, even
for passed, reused, blocked, or not-applicable outcomes. Lead with outcome and
counts. State that P0 through P3 were not evaluated because this is
validation-only. Include the full ledger export and mappings. Scope every
platform claim to its actual executor, distinguish native runs from emulation,
and name unexecuted matrix cells.

Standalone evidence is portable candidate evidence, not a transferable pass.
A later graph must recapture state and verify exact source, command,
environment, configuration, selection, and artifact identity before reuse.
