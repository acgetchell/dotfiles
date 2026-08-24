# Review Graph Node Contract

This documents the compiled native compatibility artifact and legacy direct
node format. New runtime workers return the compact `ReviewPayload` from
`runtime-contract.md`; `review_graph_runtime.py` renders and verifies the native
artifact below. Workers do not read this file.

Use this contract for every `review-graph` node. Adaptive grouped execution may
run a node in a subagent or the coordinator; isolated execution requires a
fresh worker. Both locations return the same native result and evidence
envelope.

Use the mode-specific contract below for every worker dispatch. Keep scope and
output fields stable so the coordinator can compare, gate, and synthesize
independent runs without treating review, independent checking, and validation
as interchangeable work.

## Contents

- [Scope Manifest](#scope-manifest)
- [Coordinator-Only Lifecycle Gate](#coordinator-only-lifecycle-gate)
- [Focused Review Execution Prompt](#focused-review-execution-prompt)
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
evidence_schema_version: 1
execution_profile: grouped | isolated | isolated-only | mixed
execution_location: worker | coordinator
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
skill_digest: digest of the dispatched SKILL.md
reference_digests: exact path and digest for every dispatched static reference
instruction_paths: applicable AGENTS.md or equivalent files
routing_reference_paths: applicable static router/repository guidance or empty
inspection_commands: commands that reproduce the intended diff or inventory
state_verification_command: exact read-only command that recomputes all three fingerprints
change_target: exact diff, commit, or custom target for independent review, or none
validation_requirements: exact requirement IDs and commands, or none
validation_ledger: exact reusable evidence, including verified standalone candidates, or empty
supplied_validation_results: accepted artifact identities and normalized validation evidence or empty
synthesis_bundle: canonical normalized predecessor view and digest for synthesis; otherwise empty
artifact_store: persistent session-owned or external result location
```

Do not replace either path list with phrases such as "the relevant files." Every
node-owned path must be present in `captured_scope_paths`. Focused review,
synthesis, fix, revalidation, and validation prompts receive only the fields
their contracts name. `repository-independent-review` receives only the identity,
change-target, instruction, and state-verification fields in the Independent
Review Worker Contract. Never send it `validation_ledger`,
`supplied_validation_results`, `synthesis_bundle`, prior findings, or
coordinator conclusions.

## Coordinator-Only Lifecycle Gate

Do not dispatch a worker to measure worker capacity and do not pass node reports,
findings, validation results, predecessor evidence, or coordinator conclusions
to a capacity mechanism. Apply `execution-feasibility.md` only for explicit
isolation. Adaptive grouped execution does not inspect capacity before routing;
it may attempt a useful worker and fall back to coordinator execution for the
same node.

A node that remains blocked before either worker or coordinator execution has no
Review Node Result or Validation Result. Record its planned skill and commands,
lifecycle status `blocked-before-execution`, exact blocker, and `worker created:
no` in the graph journal and reporting tables. Do not fabricate skill-loading,
inspection, fingerprint-observation, or validator evidence for that node. A
worker created but unable to load its skill is
`blocked-after-creation-before-skill-execution`; record the attempt without
adding the worker attempt to `Skills Run`. Adaptive coordinator fallback may
later produce a separate accepted execution record for the same node.

Create every worker in every profile with `fork_turns: "none"` and never dispatch
a later node through a follow-up to a completed worker. In adaptive execution,
use fresh independent workers when possible; if creation fails before accepted
evidence, record the attempt and execute that same node in the coordinator.
Isolated-only instead stops and emits the resume manifest from
`planning-contract.md`.

## Focused Review Execution Prompt

Fill every placeholder. Use the skill's absolute path so either executor cannot
silently select a similarly named workflow. A coordinator execution follows the
same prompt without the instruction to create another worker.

```text
Use $<skill-id> at <absolute-skill-path> to perform this node.

Read every applicable repository instruction file, then read the complete
SKILL.md at the path above and only its directly relevant references. Apply
exactly that one review skill. Do not load another review skill, perform broad
production synthesis unless this is explicitly a synthesis node, or spawn
another reviewer. Record a possible cross-skill concern only as a handoff.

Node ID: <node-id>
Node mode: <audit|synthesis|fix|revalidation>
Evidence schema version: 1
Execution profile: <grouped|isolated|isolated-only|mixed>
Execution location: <worker|coordinator>
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

Skill and reference digests:
<exact-path-to-digest-mapping>

Prior validation evidence:
<exact-ledger-entries-or-none>

Synthesis bundle:
<canonical-normalized-bundle-and-digest-or-none>

State verification command:
<exact-command-from-scope-manifest>

Persistent artifact store:
<exact-session-owned-or-external-location>

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
- Evidence schema version: 1
- Execution profile: <grouped|isolated|isolated-only|mixed>
- Execution location: <worker|coordinator>
- Status: <completed|no-findings|blocked>
- Selection reason: <exact dispatch reason>
- Scope fingerprint: <digest>
- Worktree fingerprint: <digest>
- Repository state fingerprint: <digest>
- Authorization: <review-only|review-and-fix>

## Skill Loading

- Skill file: <absolute path>
- Skill digest: <digest>
- References loaded: <absolute paths or none>
- Reference digests: <exact path and digest pairs or none>

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

- Handoff ID: <node-id>-handoff-<ordinal>
  - Catalog ID: <exact routing-catalog candidate>
  - Observed trigger: <concrete new applicability evidence>
  - Reason: <unreviewed contract requiring that owner>
  - Scope: <exact paths>

Write `none` when there are no handoffs.

## Limitations

<blocked evidence, untested configurations, external constraints, or none>

## Machine Evidence

<the exact canonical review block from evidence-contract.md>
```

The top heading must be exactly `# Review Node Result`, every shown section
heading must appear exactly once in this order, and the Machine Evidence block
must be the final section. Serialize its JSON exactly as required by
`evidence-contract.md`. For synthesis, populate `predecessor_evidence_ids` with
the accepted evidence ID for every dispatched predecessor, in planner order;
the final repository synthesis then appends every planner-declared exact-reuse
evidence ID. Use an empty array for every non-synthesis result.

The result header is the complete ordered list of fields between the top
heading and `## Skill Loading`. Each field appears exactly once, with no extra
header prose, and its value equals the trusted dispatch or typed evidence
identity shown above.

## Acceptance Rules

Accept a result only when:

- evidence schema version, execution profile, and execution location equal the
  dispatch; isolated profiles report a fresh worker location
- node ID, skill ID, mode, selection reason, and all three result-header
  fingerprints equal the expected dispatch identities
- the named skill file and digest are the dispatched file and digest
- every dispatched static routing/repository reference appears under
  `References loaded` with its dispatched digest
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
- the canonical Machine Evidence block matches the native report, dispatch,
  typed envelope, source/Git state, and artifact identity; for synthesis its
  predecessor evidence IDs match the planner-derived proof mapping exactly
- a fix node changed only authorized paths, maps every material change to an
  exact finding or explicit incidental-change ID, explains what changed and why,
  reports invalidated or newly required validation, matched all three identities
  before editing, reports `changed-as-reported` afterward, and changed neither
  HEAD, branch, nor index
- limitations explain every `blocked` status

Apply the same rules to a report returned after its elapsed cap. Accept it only
when the complete final report arrived and every required heading, proof, and
normal acceptance condition passes. Do not accept a status update, partial
report, interrupted response, or malformed timeout output. Preserve it as
unaccepted evidence in the resume manifest.

Do not upgrade an incomplete result to success during synthesis.

After native acceptance, persist the complete result, compute its artifact
digest, construct `ReviewEvidence`, and run `assess_review_evidence`. Preserve
`report_complete` only as compatibility metadata; the final bundle derives
completeness from the exact heading set and parsed Machine Evidence block.
Native acceptance without an accepted evidence envelope does not satisfy a
requirement.
For exact routed reuse, perform the same envelope and artifact verification but
do not create or dispatch a worker node. Preserve the routed requirement ID and
evidence ID unchanged; the reused record is the only permitted accepted review
evidence without a planned executable node.

For final repository synthesis, dispatch `repository-production-review` in
`synthesis` mode with the canonical hashed `SynthesisBundle`, accepted
predecessor IDs, routing exceptions, validation mappings, exact reuse, and
explicit user exclusions. Raw predecessor artifacts remain in the proof store
and are verified independently; do not inject them into synthesis context. It may
not capture, route, create workers, validate, fix, or perform new specialist
analysis. Require every predecessor under `Predecessor Coverage` and apply all
normal skill-loading, static-reference, structure, and fingerprint gates.
The planner, not the caller, must make this node depend on every selected
non-repository synthesis node as well as its routed audits, validators, and
additional nodes.

Fix and revalidation nodes are transition executions only. Persist their native
results in invalidation history, then recapture, reroute, and build a new
final-state plan. A final `RepositoryReviewProofExpectation` rejects any plan
that still contains either mode.

Completion receives the exact planner-derived proof expectation and
`RepositoryReviewProof`, complete review and validation records, the typed
artifact manifest, and the trusted verifier payload boundary. It invokes
`assess_evidence_bundle` itself; neither a Boolean nor a caller-constructed
`EvidenceBundleAssessment` can satisfy the repository-proof gate. Derive
executed review, validation, synthesis, independent-review, and exact-reuse
coverage only after that internal verification succeeds.

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

Use one `review-validator` execution for each independent validation unit. In
adaptive execution, prefer an independent worker and use coordinator fallback
for the same dispatch when needed. Isolated execution requires one fresh worker
per unit. Read its complete `SKILL.md` and only
`references/graph-dispatch.md`. The graph provides the planner-owned
`ValidationUnit`; the validator must not select commands from prose or load a
review skill.

Use this prompt shell:

```text
Use $review-validator at <absolute-review-validator-skill-path> to execute this
validation node.

Read every applicable repository instruction file, then read the complete skill
and its graph-dispatch reference. Apply exactly that one skill. Do not review
or fix code, assign findings, load another skill, broaden the commands, mutate
git state, or spawn another worker.

Validation Dispatch:
<exact planner-owned validation unit and trusted execution identity>

Return only the compact ValidationPayload required by that skill.
```

Persist the payload and compile it with `review_graph_runtime.py
compile-validation`. The compiler renders the native compatibility artifact,
creates `ValidationEvidence`, and runs the existing native and envelope gates.
Treat `passed`, `failed`, `reused`, and `not-applicable` as accepted evidence
states and `blocked` as an accepted blocked node state. A failed validation is
not automatically a finding; route its accepted evidence to the owning reviewer
or synthesis node for diagnosis.

## Independent Review Worker Contract

Use `repository-independent-review` only for a concrete repository-change
target, including code, documentation, tooling, or configuration changes such
as `routing-handoff.md`, `migration-acceptance.md`, and `report-contract.md`.
The worker must receive no specialist findings, coordinator diagnosis,
predecessor reports, or expected answer. Dependencies determine when it runs,
not what conclusions it sees.

Use this prompt shell:

```text
Use $repository-independent-review at <absolute-independent-review-skill-path> to independently inspect
this exact change target.

Read every applicable repository instruction file, then read the complete skill
at the path above. Apply exactly that one skill. Do not load another skill,
delegate, edit files, mutate git state, or inspect predecessor reports.

Node ID: <node-id>
Repository root: <absolute-repository-root>
Change target: <exact diff, commit, or custom inspection commands>
Planned inspected paths: <exact normalized repository-relative paths>
Scope fingerprint: <digest>
Worktree fingerprint: <digest>
Repository state fingerprint: <digest>
State verification command: <exact non-mutating command>
Applicable instruction files: <exact paths>

Run the state-verification command before and after inspection. Follow
the skill's native six-section finding and assessment format so findings remain
first. Do not invent graph finding IDs, handoff IDs, the Review Graph Envelope,
or Machine Evidence; `compile-independent-review` appends those deterministically.
Return no other graph commentary.
```

The compiler appends this envelope after the native independent-review result:

```markdown
## Review Graph Envelope

- Node ID: <node-id>
- Skill: repository-independent-review
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

The persisted independent artifact must start with exactly
`# Repository Independent Review` and contain exactly these level-two headings
in order: `Scope Inspected`, `Findings`, `No-Finding Evidence`,
`Routing Handoffs`, `Fingerprint Proof`, `Git State`, `Review Graph Envelope`,
and `Machine Evidence`, with no untyped content between the top heading and
`Scope Inspected`. Append the canonical review block from
`evidence-contract.md` under the final heading with
`result_type: independent-review-result`, `mode: independent-review`, an empty
`predecessor_evidence_ids` array, and the exact trusted `change_target`,
`inspected_paths`, and typed `handoff_ids`. The Scope Inspected and Review Graph
Envelope target/path fields must equal that dispatch provenance exactly. This
structural wrapper preserves the independent skill's native sections while
making its persisted artifact deterministically verifiable.

Invoke `compile-independent-review` with the trusted dispatch, native artifact,
derived status, and limitations. It parses ordered native Finding and Catalog
ID records, assigns graph IDs, verifies every dispatched adversarial check in
No-Finding Evidence, and writes the wrapper and metadata sidecar. The worker's
native digest remains compiler metadata; the worker never authors evidence
identities.

Derive `completed` when at least one native finding is present, `no-findings`
only when the native result says `No findings.`, and `blocked` when the target or
source identity could not be inspected. Require the result-header identities to
equal the dispatch. Accept `completed` or `no-findings` only when both observed
checks match all three identities. Every completed finding must contain exactly
one ordered `ID`, `Severity`, `Location`, `Summary`, `Evidence`, `Impact`,
`Owner`, and `Remediation` field; severity is `P0` through `P3`, location is a
tight positive line or line range under an exact dispatched repository path,
or that exact path alone for a repository-level finding, and the descriptive
fields are concrete. A line or range endpoint must not exceed the
planner-owned bound derived from the captured source identity; a deleted file
uses its captured base-side bound, and a zero bound permits only the path-alone
form. A no-findings result names the exact files, branches and boundary cases,
and tests inspected, and includes every materialized adversarial check relevant
to the dispatched surfaces; a fixed denylist is not categorical coverage. The
Scope Inspected and envelope target/path values equal the
trusted dispatch, both Result dispositions are `matched`, every native routing
handoff ID equals the typed evidence tuple, Limitations is exactly `none`, and
no source or git-state mutation occurred. Accept `blocked` when it preserves
every check that could run plus the exact unavailable target, observed mismatch,
or detected mutation; its Result dispositions must reconcile with the observed
identities, its handoffs must still match the typed tuple, and it must state one
concrete limitation. Assign stable graph-finding IDs deterministically without
rewriting the preserved native report.
