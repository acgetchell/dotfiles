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
evidence_schema_version: 1
execution_profile: standalone | grouped | isolated | isolated-only | mixed
execution_location: worker | coordinator | none
  (graph-dispatched only uses worker or coordinator; standalone must be none and
  records each executor under its `Execution` entry as `parent` or
  `subagent <node-id>`)
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
unit_coalescing_basis: source state, command or canonical recipe, working
  directories, environment/toolchain, features, platform, artifact ownership,
  and mutation/locking compatibility shared by those requirements
requirement_evidence_mapping: every requirement ID mapped to this unit and its
  exact candidate ledger entry or none
commands: ordered exact commands, including arguments
working_directories: one exact directory for each command
environment_configuration: toolchain, platform, features, target, dependency,
  instrumentation, service, and relevant environment identity
command_identity_digest: canonical SHA-256 digest of the exact commands,
  corresponding working directories, and canonical recipe
environment_digest: canonical SHA-256 digest of the environment, toolchain,
  features, platform, artifact owner, and mutation/locking identity
command_mutation_classification: non-mutating, with exact definition or policy basis
expected_evidence: what successful execution must demonstrate
dependency_policy: stop-on-failure | continue-independent
execution_strategy: sequential | parallel-independent
independence_basis: prerequisite and shared-resource analysis for every parallel unit, or none
allowed_artifacts: exact approved records of path, kind, repository status, and
  optional expected artifact ID or content digest in the exact
  `sha256:<64-lowercase-hex>` representation; status is ignored or
  outside-repository
validation_ledger: exact reusable entries or none
elapsed_time_budget: total budget and any per-command limits
instruction_paths: applicable repository instructions
skill_digest: digest of review-validator/SKILL.md
reference_digests: exact path and digest for this result contract
artifact_store: persistent session-owned or external result location
```

### Canonical Validation Dispatch Digests

Produce both dispatch digests with the graph planner's `_sha256_json`
deterministic JSON serializer. The command-identity input is one object whose
fields serialize in this order: `canonical_recipe`, `commands`, and
`working_directories`. The environment input is one object whose fields
serialize in this order: `allowed_artifacts`, `artifact_owner`, `environment`,
`features`, `mutation_lock`, `platform`, and `toolchain`. Each element of
`allowed_artifacts` is one object whose fields serialize in this order:
`artifact_digest`, `artifact_id`, `kind`, `path`, and `repository_status`.

Sort object keys lexicographically at every level; preserve array element
order; serialize tuples as JSON arrays and absent optional values as JSON
`null`; escape non-ASCII characters with JSON `\u` escapes; use `,` and `:` as
separators without added whitespace or a trailing newline; then encode the JSON
text as UTF-8. Hash those exact bytes with SHA-256 and report `sha256:` followed
immediately by exactly 64 lowercase hexadecimal characters (`[0-9a-f]`).

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
- Evidence schema version: 1
- Execution profile: <standalone|grouped|isolated|isolated-only|mixed>
- Execution location: <worker|coordinator|none>
  - graph-dispatched results: worker or coordinator
  - standalone results: none; record parent or subagent executor identity in each
    `Execution` entry instead
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
- Skill digest: <digest>
- References loaded: <absolute paths>
- Reference digests: <exact path and digest pairs>

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
- Command identity digest: <canonical digest from the exact dispatched commands,
  working directories, and canonical recipe>
- Environment digest: <canonical digest from the exact dispatched environment,
  toolchain, features, platform, artifact owner, and mutation/locking identity>
- Requirement-to-evidence mapping:
  - <requirement-id>: <this unit and exact candidate ledger entry, or none>
- Meaningful skips: <command and reason or none>
- Execution strategy: <sequential|parallel-independent>
- Dependency policy: <stop-on-failure|continue-independent>
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
  - Evidence: <concise stdout/stderr facts>
  - Log or artifact: <none or a JSON list of exact path, artifact_id, and
    artifact_digest objects>

Write `none` when no command executed.

## Reused Evidence

- Ledger entry: <exact entry identity>
  - Requirement IDs: <IDs satisfied>
  - Match basis: <state, command, environment, configuration, and selection>

## Artifacts

- Path: <exact path>
  - Artifact ID: <opaque ID|none>
  - Artifact digest: <sha256: followed by exactly 64 lowercase hexadecimal characters>
  - Kind: <build|cache|coverage|log|other>
  - Repository status: <ignored|outside-repository>

Compute each digest from the completed artifact before returning the result. A
regular file uses `sha256:` followed immediately by exactly 64 lowercase
hexadecimal characters containing the SHA-256 of its raw bytes. A directory
uses this canonical `directory-artifact-v1` format:

1. Recursively enumerate regular files without following symbolic links. Empty
   directories contribute no records; reject symbolic links and other special
   entries.
2. Express each path relative to the artifact root with `/` separators,
   normalize every component to Unicode NFC, encode it as UTF-8, and reject an
   absolute path, `.`, `..`, an empty component, invalid UTF-8, or a normalized
   path collision.
3. Sort records by the unsigned lexicographic order of the normalized UTF-8
   path bytes. For each file, append an unsigned 64-bit big-endian path-byte
   length, the path bytes, and the raw 32-byte SHA-256 digest of the file bytes.
4. Form the exact outer digest input as the ASCII bytes
   `review-validator-directory-artifact-v1\0`, followed by the unsigned 64-bit
   big-endian record count and the concatenated records. Report `sha256:`
   followed immediately by exactly 64 lowercase hexadecimal characters
   containing the SHA-256 of those complete bytes.

Digest generation and evidence acceptance must both use this exact format and
must compare the regenerated digest before accepting the artifact. An artifact
ID remains a separate locator and is never part of, or a substitute for, the
content digest.

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
- Command identity digest: <exact dispatch digest>
- Environment digest: <exact dispatch digest>
- Source and Git state: <unchanged|changed|unknown>
- Provenance: <node ID, invocation, status, and exact result containing the evidence>
- Handoff: <standalone: provide this complete result or its persisted artifact;
  graph-dispatched: returned directly to the dispatching review-graph>

## Limitations

<unavailable configurations, skipped dependent commands, stale evidence, or none>

## Machine Evidence

<the exact canonical validation block from
review-graph/references/evidence-contract.md>
```

The top heading must be exactly `# Validation Result`, every shown section
heading must appear exactly once in this order, and the Machine Evidence block
must be the final section. Serialize its one-line JSON object between the exact
markers from the review-graph evidence contract; do not use YAML or
frontmatter. The block must bind the artifact/evidence/node identity, validation
status, requirement IDs, expected/before/after fingerprints, command and
environment digests, and source/Git mutation to this native result.

The result header is the complete ordered list of fields between the top
heading and `## Outcome Summary`. Each field appears exactly once, with no
extra header prose, and its value equals the trusted invocation, dispatch, or
typed evidence identity shown above.

## Acceptance Rules

Accept a result only when:

- evidence schema version, execution profile, and execution location equal the
  actual dispatch; graph-dispatched execution must use `worker` or `coordinator`
  and standalone execution must use `none`; graph-dispatched execution does not
  create another worker
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
- in graph-dispatched mode, Validation Plan equals the complete canonical typed
  dispatch: request, scope, capture, paths, authorities, per-requirement command
  plans, coalescing identity, command/environment digests, evidence mappings,
  skips, strategy, independence basis, and planning blocker
- the named skill and reference paths and digests are the files actually loaded
- graph-dispatched Skill Loading equals the validator skill path/digest and
  ordered reference path/digest pairs from the typed expectation exactly
- `passed`, `failed`, `reused`, and `not-applicable` ran state verification
  before and after, both observations matched all three dispatch identities, and
  no source or Git-state mutation occurred beyond reported allowed artifacts
- `blocked` records every state check that could run plus the observed mismatch
  or blocker; an unavailable or mismatched check is valid blocked evidence and
  is not required to report `matched`
- every requirement ID has exactly one disposition; in graph-dispatched mode,
  Requirements equals the typed ordered IDs, status-derived dispositions, and
  exact execution or reused-evidence identities
- the coalescing basis covers source state, command or canonical recipe,
  working directories, environment/toolchain, features, platform, artifact
  ownership, and mutation/locking compatibility; every requirement maps
  exactly once to this unit and any candidate evidence
- command and environment digests use the canonical validation-dispatch
  serialization above over the exact coalesced dispatch fields, are repeated
  exactly in the result, and match the graph's independently derived
  `ValidationEvidenceExpectation` values
- every executed command exactly matches the dispatch and reports working
  directory, executor, environment, result, exit code, elapsed time, evidence,
  and log or artifact references exactly once in the shown order; working directory and
  environment equal the dispatched unit, `passed` uses exit code `0` plus
  concrete elapsed time and evidence, `failed` uses a nonzero integer exit code
  plus concrete elapsed time and evidence, and `blocked` or `not-run` fields
  reconcile with their result; evidence contains concrete stdout/stderr facts;
  artifact references are `none` or a JSON list whose exact path, optional ID,
  and required digest resolve to one reported artifact identity
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
- artifacts exactly equal the dispatch-approved paths, kinds, and
  ignored/outside-repository statuses; every reported artifact has a digest in
  the exact `sha256:<64-lowercase-hex>` representation regenerated from the
  completed file bytes or the canonical `directory-artifact-v1` format above,
  and any expected artifact ID or digest supplied by the dispatch matches
  exactly; unapproved or mismatched-identity artifacts are rejected
- `passed`, `failed`, `reused`, and `not-applicable` report no
  source-controlled file or Git-state mutation; a blocked result reports any
  detected mutation exactly
- the Validation Ledger Export repeats the result identities exactly; use
  `candidate-for-reuse` only for `passed` or `reused` evidence with unchanged
  source and Git state, `evidence-only` for failed, not-applicable, or
  non-mutating blocked evidence, and `ineligible` when identity is missing,
  stale, or mutated; graph-dispatched results use consumer `review-graph` and
  match every requirement, command/selection, fingerprint, environment,
  digest, state, provenance, and handoff field from the typed evidence
- the exact top heading, ordered required section headings, and canonical
  Machine Evidence block are complete and match the dispatch and native result
  semantics

Do not convert `failed` or `blocked` evidence into a pass during coordination or
synthesis.

For a graph dispatch, the coordinator persists this complete result, computes
its artifact digest, constructs `ValidationEvidence`, and runs
`assess_validation_evidence`. The final evidence bundle then reparses the
trusted artifact bytes and requires the native Machine Evidence block to match
that envelope exactly. This native result does not satisfy a graph requirement
until both gates accept it.
