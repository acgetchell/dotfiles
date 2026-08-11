# Review Validator Result Contract

Use this contract for every standalone or graph-dispatched validation unit.

## Contents

- [Invocation Modes](#invocation-modes)
- [Validation Dispatch](#validation-dispatch)
- [Validation Result](#validation-result)
- [Acceptance Rules](#acceptance-rules)

## Invocation Modes

### Graph-dispatched

Accept a complete Validation Dispatch from `review-graph`. Do not discover,
replace, add, remove, or broaden commands. Return `blocked` when a required field
is absent or the supplied plan cannot execute exactly.

### Standalone

Derive the Validation Dispatch before execution. Record:

```text
invocation: standalone
requested_scope: branch | staged | worktree | baseline | release
capture_command: exact capture_scope.py command
captured_scope_paths: exact manifest paths
authorities_inspected: exact instruction, task, manifest, preset, CI, or doc paths
selection: requirement IDs, authority, rationale, exact commands, and configuration
mutation_classification: non-mutating, with repository-owned definition or policy basis
meaningful_skips: authoritative commands considered but not selected, with reasons
execution_strategy: sequential or parallel-independent, with the independence basis
```

The internally derived dispatch is then governed by the same execution and
result rules as a graph dispatch. Discovery is validation routing, not code
review. If discovery cannot establish a safe authoritative command, return a
blocked plan with the exact gap.

## Validation Dispatch

Require these fields from the graph or populate them in standalone mode before
execution:

```text
node_id: stable graph identifier or standalone-validation-<scope-digest-prefix>
invocation: graph-dispatched | standalone
repository_root: absolute path
request: exact validation request
authorization: validation-only
requested_scope: branch | staged | worktree | baseline | release
captured_scope_paths: exact paths from the capture manifest, or none
scope_fingerprint: captured review-scope digest
captured_worktree_fingerprint: digest for files commands will execute
repository_state_fingerprint: content digest covering HEAD, branch, index,
  tracked worktree files, and nonignored untracked files
state_verification_command: exact read-only command that recomputes all three digests
requirement_ids: exact validation requirements owned by this unit
unit_coalescing_basis: source state, command or canonical recipe,
  environment/toolchain, features, platform, artifact ownership, and
  mutation/locking compatibility shared by those requirements
requirement_evidence_mapping: every requirement ID mapped to this unit and its
  exact candidate ledger entry or none
commands: ordered exact commands, including arguments
working_directories: one exact directory for each command
environment_configuration: toolchain, platform, features, target, dependency,
  instrumentation, service, and relevant environment identity
command_mutation_classification: non-mutating, with exact definition or policy basis
expected_evidence: what successful execution must demonstrate
dependency_policy: stop-on-failure | continue-independent
execution_strategy: sequential | parallel-independent
independence_basis: prerequisite and shared-resource analysis for every parallel unit, or none
allowed_artifacts: approved ignored paths or external artifact directory
validation_ledger: exact reusable entries or none
elapsed_time_budget: total budget and any per-command limits
instruction_paths: applicable repository instructions
```

Do not accept phrases such as “run the relevant tests” in place of exact
commands, configurations, or selections. Do not accept a state-verification
command that mutates source or Git state.

## Validation Result

Return every heading, using `none` when a section has no entries.

```markdown
# Validation Result

- Node ID: <node-id>
- Skill: review-validator
- Invocation: <graph-dispatched|standalone>
- Status: <passed|failed|blocked|reused|not-applicable>
- Scope fingerprint: <digest|none>
- Worktree fingerprint: <digest|none>
- Repository state fingerprint: <digest|none>

## Outcome Summary

- Overall: <PASSED|FAILED|BLOCKED|REUSED|NOT-APPLICABLE>
- Requirements: <passed N; failed N; blocked N; reused N>
- Executions: <passed N; failed N; blocked N; not-run N>
- Review findings: not evaluated (validation-only)
- Review severities: P0 not evaluated; P1 not evaluated; P2 not evaluated; P3 not evaluated

## Skill Loading

- Skill file: <absolute path>
- References loaded: <absolute paths>

## Validation Plan

- Request: <exact request>
- Requested scope: <branch|staged|worktree|baseline|release>
- Capture command: <exact command>
- Captured paths: <exact paths or none>
- Authorities inspected: <exact paths or graph dispatch>
- Requirement: <requirement-id>
  - Authority: <exact path and recipe/job/config entry or graph dispatch>
  - Selection reason: <scope coverage reason>
  - Command: <exact command or none>
  - Working directory: <absolute path>
  - Configuration: <complete relevant identity>
  - Mutation classification: <non-mutating and exact definition or policy basis>
  - Expected evidence: <observable success evidence>
  - Budget: <bounded duration>
- Coalescing basis: <complete compatibility identity for this validator unit>
- Requirement-to-evidence mapping:
  - <requirement-id>: <this unit and exact candidate ledger entry, or none>
- Meaningful skips: <command and reason or none>
- Execution strategy: <sequential|parallel-independent>
- Independence basis: <prerequisite and shared-resource analysis or none>
- Planning blocker: <exact gap or none>

## State Verification

- Before command: <exact command>
  - Observed scope fingerprint: <digest|none>
  - Observed worktree fingerprint: <digest|none>
  - Observed repository state fingerprint: <digest|none>
  - Result: <matched|mismatched|blocked>
- After command: <exact command>
  - Observed scope fingerprint: <digest|none>
  - Observed worktree fingerprint: <digest|none>
  - Observed repository state fingerprint: <digest|none>
  - Result: <matched|mismatched|blocked>

## Requirements

- Requirement: <requirement-id>
  - Disposition: <passed|failed|blocked|reused>
  - Evidence: <execution IDs or exact ledger entries>

## Executions

- Execution ID: <node-id>-exec-<ordinal>
  - Executor: <parent|subagent node-id>
  - Command: <exact command>
  - Working directory: <absolute path>
  - Environment/configuration: <complete relevant identity>
  - Result: <passed|failed|blocked|not-run>
  - Exit code: <integer|none>
  - Elapsed: <duration|none>
  - Evidence: <concise stdout/stderr facts, not an unsupported conclusion>
  - Log or artifact: <path outside source or none>

Write `none` when no command executed.

## Reused Evidence

- Ledger entry: <exact entry identity>
  - Requirement IDs: <IDs satisfied>
  - Match basis: <state, command, environment, configuration, and selection>

## Artifacts

- Path: <exact path>
  - Kind: <build|cache|coverage|log|other>
  - Repository status: <ignored|outside-repository>

## Source And Git State

- Source-controlled files changed: <exact paths or none>
- Git state mutated: <yes|no|blocked>

## Validation Ledger Export

- Evidence ID: <review-validator:node-id:repository-state-prefix>
- Consumer: review-graph
- Disposition: <candidate-for-reuse|evidence-only|ineligible>
- Requirement IDs: <exact IDs or none>
- Commands and selections: <exact execution or reused-evidence IDs>
- Scope fingerprint: <digest|none>
- Worktree fingerprint: <digest|none>
- Repository state fingerprint: <digest|none>
- Environment/configuration: <complete relevant identity or none>
- Source and Git state: <unchanged|changed|unknown>
- Provenance: <node ID, invocation, status, and exact result containing the evidence>
- Handoff: <standalone: provide this complete result or its persisted artifact;
  graph-dispatched: returned directly to the dispatching review-graph>

## Limitations

<unavailable configurations, skipped dependent commands, stale evidence, or none>
```

## Acceptance Rules

Accept a result only when:

- `Invocation` identifies the actual mode
- the Outcome Summary uppercase outcome matches `Status`, its counts reconcile
  exactly with Requirements and Executions, and review severities remain
  `not evaluated (validation-only)`
- in graph-dispatched mode, node ID and all three result-header fingerprints
  equal the supplied dispatch identities; observed identities belong under State
  Verification
- in standalone mode, the result records the exact capture command, manifest
  identity, authority paths, derived requirements, selected commands,
  configurations, budgets, and meaningful skips or planning blocker
- the named skill and reference paths are the files actually loaded
- `passed`, `failed`, `reused`, and `not-applicable` ran state verification
  before and after, both observations matched all three dispatch identities, and
  no source or Git-state mutation occurred beyond reported allowed artifacts
- `blocked` records every state check that could run plus the observed mismatch
  or blocker; an unavailable or mismatched check is valid blocked evidence and
  is not required to report `matched`
- every requirement ID has exactly one disposition
- the coalescing basis covers source state, command or canonical recipe,
  environment/toolchain, features, platform, artifact ownership, and
  mutation/locking compatibility; every requirement maps exactly once to this
  unit and any candidate evidence
- every executed command exactly matches the dispatch and reports working
  directory, executor, environment, result, exit code, elapsed time, and evidence
- every candidate and executed command is classified from repository-owned
  evidence; mutating commands are never executed under `validation-only`
- every parallel unit records a concrete independence basis; each subagent result
  matches the dispatched fingerprints and execution identity, and the parent
  performed the final state check and status reconciliation
- every reuse names a matching ledger entry and its full match basis
- `blocked` takes precedence when any requirement could not execute or source
  identity was lost; otherwise `failed` means at least one execution failed,
  `passed` means every requirement is passed or reused and at least one command
  executed, `reused` means every nonempty requirement set was reused without
  execution, and `not-applicable` means the plan had zero requirements and zero
  commands because capture was empty or discovery proved no validation applied
- artifacts are ignored or outside the repository and are fully reported
- `passed`, `failed`, `reused`, and `not-applicable` report no
  source-controlled file or Git-state mutation; a blocked result reports any
  detected mutation exactly
- the Validation Ledger Export repeats the result identities exactly; use
  `candidate-for-reuse` only for `passed` or `reused` evidence with unchanged
  source and Git state, `evidence-only` for failed, not-applicable, or
  non-mutating blocked evidence, and `ineligible` when identity is missing,
  stale, or mutated

Do not convert `failed` or `blocked` evidence into a pass during coordination or
synthesis.
