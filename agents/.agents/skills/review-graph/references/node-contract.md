# Review Graph Node Contract

Use the mode-specific contract below for every worker dispatch. Keep scope and
output fields stable so the coordinator can compare, gate, and synthesize
independent runs without treating review, independent checking, and validation
as interchangeable work.

## Contents

- [Scope Manifest](#scope-manifest)
- [Coordinator-Only Lifecycle Gate](#coordinator-only-lifecycle-gate)
- [Focused Review Worker Prompt](#focused-review-worker-prompt)
- [Review Node Result](#review-node-result)
- [Acceptance Rules](#acceptance-rules)
- [Validation Worker Contract](#validation-worker-contract)
- [Independent Review Worker Contract](#independent-review-worker-contract)

## Scope Manifest

Maintain these fields in the coordinator manifest. Pass only the mode-specific
subset required by each worker contract; do not send the complete manifest to
every node:

```text
repository_root: absolute path
request: exact user request relevant to this node
authorization: review-only | review-and-fix
graph_mode: branch | staged | worktree | pull-request | release | baseline
capture_mode: branch | staged | worktree | baseline
base_ref: explicit value or none
merge_base: exact commit or none
head: exact commit
scope_fingerprint: digest from capture_scope.py
captured_worktree_fingerprint: digest from capture_scope.py
repository_state_fingerprint: whole-repository content digest from capture_scope.py
captured_scope_paths: exact paths included by capture_scope.py
node_scope_paths: exact captured paths owned by this node
selection_reason: why this exact skill owns the assigned contract
instruction_paths: applicable AGENTS.md or equivalent files
routing_reference_paths: applicable static router/repository guidance or empty
inspection_commands: commands that reproduce the intended diff or inventory
state_verification_command: exact read-only command that recomputes all three fingerprints
change_target: exact diff, commit, or custom target for review-agent, or none
validation_requirements: exact requirement IDs and commands, or none
validation_ledger: exact reusable evidence, including verified standalone candidates, or empty
supplied_validation_results: complete user-supplied standalone Validation Results or empty
predecessor_reports: complete reports for synthesis, fix, or revalidation; otherwise empty
```

Do not replace either path list with phrases such as "the relevant files." Every
node-owned path must be present in `captured_scope_paths`. Focused review,
synthesis, fix, revalidation, and validation prompts receive only the fields
their contracts name. An independent `review-agent` receives only the identity,
change-target, instruction, and state-verification fields in the Independent
Review Worker Contract. Never send it `validation_ledger`,
`supplied_validation_results`, `predecessor_reports`, prior findings, or
coordinator conclusions.

## Coordinator-Only Lifecycle Gate

Do not dispatch a worker to measure worker capacity and do not pass node reports,
findings, validation results, predecessor evidence, or coordinator conclusions
to a capacity mechanism. Apply `execution-feasibility.md` using safe aggregate
concurrent-capacity metadata before any node prompt exists. Treat lifetime
fresh-creation metadata as optional; its absence is not a lifecycle-gate
failure.

A node blocked before worker creation has no Review Node Result or Validation
Result. Record its planned skill and commands, lifecycle status
`blocked-before-execution`, exact blocker, and `worker created: no` in the graph
journal and reporting tables. Do not fabricate skill-loading, inspection,
fingerprint-observation, or validator evidence for that node. A worker created
but unable to load its skill is `blocked-after-creation-before-skill-execution`;
record the attempt without adding the skill to `Skills Run`.

Create a fresh no-inherited-turn worker for every node. Never dispatch a later
node through a follow-up to a completed worker. If creation fails or the hard
deadline leaves no dispatch window, preserve completed reports and mark every
undispatched node `blocked-before-execution` with the exact shared blocker.

## Focused Review Worker Prompt

Fill every placeholder. Use the skill's absolute path so the worker cannot
silently select a similarly named workflow.

```text
Use $<skill-id> at <absolute-skill-path> to perform this node.

Read every applicable repository instruction file, then read the complete
SKILL.md at the path above and only its directly relevant references. Apply
exactly that one review skill. Do not load another review skill, perform broad
production synthesis unless this is explicitly a synthesis node, or spawn
another reviewer. Record a possible cross-skill concern only as a handoff.

Node ID: <node-id>
Node mode: <audit|synthesis|fix|revalidation>
Selection reason: <why-this-skill-owns-this-node>
Repository root: <absolute-repository-root>
Authorization: <review-only|review-and-fix>
Scope manifest:
<complete-scope-manifest>

Node-owned scope paths (node_scope_paths):
<exact-path-list>

Applicable instruction files:
<exact-instruction-paths>

Applicable static routing/repository references:
<exact-reference-paths-or-none>

Prior validation evidence:
<exact-ledger-entries-or-none>

Predecessor reports:
<complete-reports-or-none>

State verification command:
<exact-command-from-scope-manifest>

For audit and synthesis nodes, do not edit source files. For fix nodes, edit
only verified in-scope findings and do not mutate git state. Inspect the scope
yourself; do not infer completion from the manifest or predecessor reports.
Load every dispatched static routing/repository reference as domain guidance;
it is not permission to load another skill or execute an orchestrator loop.
For staged nodes, inspect the index and staged diff as authoritative; key any
validator that executes current files to `captured_worktree_fingerprint` and
`repository_state_fingerprint`. Run the state-verification command before and
after the node. Read-only modes must preserve all three identities. A fix node
must report the changed identities and every changed path after its authorized
edits without modifying HEAD, branch, or index.
Return exactly the Review Node Result format below, with no prose before it.
```

## Review Node Result

Require every heading, using `none` when a section has no entries.

```markdown
# Review Node Result

- Node ID: <node-id>
- Skill: <skill-id>
- Mode: <audit|synthesis|fix|revalidation>
- Status: <completed|no-findings|blocked>
- Selection reason: <exact dispatch reason>
- Scope fingerprint: <digest>
- Worktree fingerprint: <digest>
- Repository state fingerprint: <digest>
- Authorization: <review-only|review-and-fix>

## Skill Loading

- Skill file: <absolute path>
- References loaded: <absolute paths or none>

## State Verification

- Command: <exact state-verification command>
- Before:
  - Observed scope fingerprint: <digest|none>
  - Observed worktree fingerprint: <digest|none>
  - Observed repository state fingerprint: <digest|none>
  - Result: <matched|mismatched|blocked>
- After:
  - Observed scope fingerprint: <digest|none>
  - Observed worktree fingerprint: <digest|none>
  - Observed repository state fingerprint: <digest|none>
  - Result: <matched|changed-as-reported|mismatched|blocked>
- Changed repository paths: <exact paths or none>
- HEAD, branch, or index mutated: <yes|no|blocked>

## Scope Inspected

- Files: <exact paths>
- Nearby contract owners: <exact paths or none>

## Findings

- ID: <skill-id>-<ordinal>
  - Severity: <P0|P1|P2|P3>
  - Location: <path:line or path>
  - Summary: <concise actionable finding>
  - Evidence: <specific observed behavior and violated contract>
  - Remediation: <smallest safe correction>

Write `none` when there are no findings.

## Validation

- Requirement ID: <stable requirement ID>
  - Command: <exact command or none>
  - Evidence fingerprints: <scope, worktree, and repository-state digests>
  - Environment/configuration: <relevant identity>
  - Result: <passed|failed|blocked|reused>
  - Evidence source: <this node or exact ledger entry>

## Validation Requirements

- Requirement ID: <stable requirement ID>
  - Owner: <skill ID>
  - Reason: <risk or contract requiring evidence>
  - Commands: <ordered exact commands>
  - Working directories: <exact directories>
  - Environment/configuration: <complete relevant identity>
  - Expected evidence: <what successful execution demonstrates>
  - Dependency policy: <stop-on-failure|continue-independent>
  - Disposition: <required|satisfied|invalidated|blocked>
  - Ledger evidence: <exact entry or none>

Write `none` only when the node neither owns nor invalidates validation. Every
reported validation execution must name one listed requirement. Fix nodes must
list every requirement invalidated or introduced by their changes.

## Predecessor Coverage

- Node: <predecessor-node-id>
  - Disposition: <consumed|blocked|not-applicable>
  - Contribution: <findings or evidence incorporated, or reason none>

Write `none` for every non-synthesis node. A synthesis node must list every
dispatched predecessor exactly once.

## Changes

- Change ID: <node-id>-change-<ordinal>
  - Finding IDs: <exact IDs, or incidental-<node-id>-<ordinal>>
  - Files: <exact paths>
  - What changed: <specific behavior or contract change>
  - Why: <evidence-backed reason this is the smallest safe correction>
  - Contract preserved: <invariants, compatibility, or tradeoffs preserved>

Write `none` when no files changed. Audit, synthesis, and revalidation nodes
must report `none`. Do not use only generic descriptions such as “cleanup,”
“hardening,” or “addressed findings.”

## Handoffs

- Suggested skill: <skill-id>
  - Reason: <unreviewed contract requiring that owner>
  - Scope: <exact paths>

Write `none` when there are no handoffs.

## Limitations

<blocked evidence, untested configurations, external constraints, or none>
```

## Acceptance Rules

Accept a result only when:

- node ID, skill ID, mode, selection reason, and all three result-header
  fingerprints equal the expected dispatch identities
- the named skill file is the dispatched file
- every dispatched static routing/repository reference appears under
  `References loaded`
- inspected files overlap the assigned scope or the report explains why the
  scope contains no applicable contract
- `completed` and `no-findings` results contain concrete inspection evidence
- audit, synthesis, and revalidation results with `completed` or `no-findings`
  matched all three state identities before and after and changed no repository
  path or git state
- a `blocked` read-only result records every state check that could run plus the
  exact mismatch or blocker; mismatched observed identities are valid blocked
  evidence and are not required to report `matched`
- every finding has severity, location, evidence, and remediation
- every validator is tied to the applicable scope or worktree fingerprint and
  configuration through the dispatch manifest or report
- every validation execution maps to one declared requirement and every
  requirement has an exact command plan, matching ledger evidence, or a stated
  blocker
- every synthesis predecessor appears exactly once under `Predecessor Coverage`
- a fix node changed only authorized paths, maps every material change to an
  exact finding or explicit incidental-change ID, explains what changed and why,
  reports invalidated or newly required validation, matched all three identities
  before editing, reports `changed-as-reported` afterward, and changed neither
  HEAD, branch, nor index
- limitations explain every `blocked` status

Do not upgrade an incomplete result to success during synthesis.

## Validation Worker Contract

For a user-supplied standalone result, first require its complete native
Validation Result, including Outcome Summary and Validation Ledger Export.
Recompute the current graph identities and validate the result against the
validator's standalone acceptance rules. When it remains an exact
`candidate-for-reuse`, place its complete matching evidence in
`validation_ledger` and dispatch the normal graph validation worker. The worker
must verify the ledger entry and return `reused`; an imported result never
replaces the required graph validation node.

Treat `failed`, `blocked`, and `not-applicable` imports as evidence only, and
stale, malformed, or mutating imports as ineligible. Preserve all of them in the
journal. A validator does not assign P0-P3 severity; send failed evidence to a
review owner before it can become a finding.

Use one fresh `review-validator` worker for each independent validation unit.
Read its complete `SKILL.md` and
`references/result-contract.md`, then fill that skill's Validation Dispatch
verbatim. The graph must provide exact commands; the validator must not select
them from prose or load a review skill.

Use this prompt shell:

```text
Use $review-validator at <absolute-review-validator-skill-path> to execute this
validation node.

Read every applicable repository instruction file, then read the complete skill
and its result-contract reference. Apply exactly that one skill. Do not review
or fix code, assign findings, load another skill, broaden the commands, mutate
git state, or spawn another worker.

Validation Dispatch:
<complete-dispatch-from-review-validator-result-contract>

Return exactly the Validation Result format required by that skill, with no
prose before it.
```

Accept the native Validation Result only when it satisfies every acceptance rule
in `review-validator/references/result-contract.md`. Treat `passed`, `failed`,
`reused`, and `not-applicable` as accepted evidence states and `blocked` as an
accepted blocked node state. A failed validation is not automatically a finding;
route its raw evidence to the owning reviewer or synthesis node for diagnosis.

## Independent Review Worker Contract

Use the active system `review-agent` only for a concrete code-change target.
The worker must receive no specialist findings, coordinator diagnosis,
predecessor reports, or expected answer. Dependencies determine when it runs,
not what conclusions it sees.

Use this prompt shell:

```text
Use $review-agent at <absolute-review-agent-skill-path> to independently inspect
this exact change target.

Read every applicable repository instruction file, then read the complete skill
at the path above. Apply exactly that one skill. Do not load another skill,
delegate, edit files, mutate git state, or inspect predecessor reports.

Node ID: <node-id>
Repository root: <absolute-repository-root>
Change target: <exact diff, commit, or custom inspection commands>
Scope fingerprint: <digest>
Worktree fingerprint: <digest>
Repository state fingerprint: <digest>
State verification command: <exact non-mutating command>
Applicable instruction files: <exact paths>

Run the state-verification command before and after inspection. Follow
review-agent's native finding and assessment format so findings remain first.
Then append the Review Graph Envelope below. Return no other graph commentary.
```

Require this envelope after the native review-agent result:

```markdown
## Review Graph Envelope

- Node ID: <node-id>
- Skill: review-agent
- Mode: independent-review
- Status: <completed|no-findings|blocked>
- Scope fingerprint: <digest>
- Worktree fingerprint: <digest>
- Repository state fingerprint: <digest>
- Skill file: <absolute path>
- Change target: <exact target or inspection commands>
- Files inspected: <exact paths or none>
- State verification before:
  - Observed scope fingerprint: <digest|none>
  - Observed worktree fingerprint: <digest|none>
  - Observed repository state fingerprint: <digest|none>
  - Result: <matched|mismatched|blocked>
- State verification after:
  - Observed scope fingerprint: <digest|none>
  - Observed worktree fingerprint: <digest|none>
  - Observed repository state fingerprint: <digest|none>
  - Result: <matched|mismatched|blocked>
- Source-controlled files changed: <exact paths or none>
- Git state mutated: <yes|no|blocked>
- Limitations: <test gaps, unavailable target, or none>
```

Derive `completed` when at least one native finding is present, `no-findings`
only when the native result says `No findings.`, and `blocked` when the target or
source identity could not be inspected. Require the result-header identities to
equal the dispatch. Accept `completed` or `no-findings` only when both observed
checks match all three identities, findings follow review-agent's severity and
location format, inspected files overlap the nonempty target, and no source or
git-state mutation occurred. Accept `blocked` when it preserves every check that
could run plus the exact unavailable target, observed mismatch, or detected
mutation; blocked state checks need not say `matched`. Assign stable graph
finding IDs without rewriting the preserved native report.
