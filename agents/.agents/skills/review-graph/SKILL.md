---
name: review-graph
description: "Execute broad repository reviews as an auditable graph of isolated subagents, with focused reviewers, independent review-agent checks, dedicated review-validator executions, and complete evidence reconciliation. Use directly or as the execution kernel beneath repository and language review entrypoints for branch, staged, pull-request, release-readiness, whole-repository, or fix-all reviews when specialist passes must behave like separate manual skill invocations and every finding, change, check, and validator must be accounted for."
---

# Review Graph

Act as a graph coordinator. Route work, dispatch isolated workers, preserve their
raw evidence, maintain the graph journal, and enforce completion gates. Do not
perform specialist review in the coordinator context. Accept either a direct
user request or one normalized scope/routing handoff from a thin review
entrypoint.

## Execution Contract

- Require a subagent mechanism that supports fresh workers without inherited
  turns and at least one free concurrent worker slot. Treat a lifetime
  fresh-creation count as optional: record and honor it when the runtime exposes
  one, but do not block merely because it is unavailable. Do not fall back to
  loading several specialist skills into the coordinator context.
- Spawn every worker with no inherited conversation history when the
  surface supports it (`fork_turns: "none"` for Codex collaboration tools).
- Invoke exactly one skill per worker. A focused reviewer may identify a handoff
  but must not load another review skill or spawn its own reviewer. A
  `review-agent` or `review-validator` worker must not load a focused skill.
- Run workers sequentially to reproduce manual one-at-a-time skill invocation.
  Create a new worker for every node and fresh-worker retry; never reuse a
  completed worker through a follow-up task for a different node.
- Give every node an explicit elapsed-time cap. Default a narrow read-only
  review node to five minutes. Budget validation nodes from their exact command
  plan rather than inheriting the review default. Treat node caps as safety
  limits, not time reservations. When a hard global deadline exists, dispatch
  while time remains, preserve a final-reconciliation reserve, and account for
  every node that the deadline prevents from running.
- Keep audit, independent-review, validation, synthesis, and revalidation nodes
  source-read-only. Treat approved ignored build products and test caches as
  validator artifacts, not source edits.
- Preserve each worker's complete final report until synthesis. Do not replace a
  report with coordinator recollection or a shorter intermediate summary.
- Maintain a coordinator-owned graph journal from routing through final output.
  Record routing authorities consulted, selection and skip reasons, exact node
  results, finding dispositions, change rationale, invalidation/revalidation,
  and validation-ledger entries. Do not reconstruct this journal from memory at
  the end.
- Persist the journal and complete node reports outside the reviewed repository
  after every accepted or blocked result. Prefer session-owned keyed storage;
  otherwise use a unique temporary directory. Do not rely on conversation
  context alone or place review artifacts in the repository.
- Never claim that a router or specialist ran merely because its `SKILL.md` was
  read. A skill executed only after its dedicated worker was created and loaded
  it; a conforming result separately determines whether the node was accepted or
  blocked after execution.
- Use [`review-validator`](../review-validator/SKILL.md) as the dedicated gate
  for every planned validation unit. Review skills own the requirements and may
  produce reusable focused evidence; the validator either verifies that exact
  reuse or executes the uncovered commands. It does not select scope, diagnose
  failures, or apply fixes. Treat a missing validator skill as a blocked gate.
- A standalone `review-validator` result is not automatically available to the
  graph. When the user supplies its complete native result or persisted
  artifact, preserve it as external candidate evidence and apply the ingestion
  rules below. Never infer a prior result from commentary or claim cross-task
  reuse without the actual result.
- Use the active system `review-agent` as an independent defect check for an
  exact branch, staged, worktree, commit, or pull-request change. Do not give it
  specialist findings or reports. Skip it with a recorded reason for a
  whole-repository baseline or any scope without a concrete change target.
  Treat an unavailable `review-agent` as a blocked independent-review gate.
- Do not create nested sub-graph orchestrator workers merely to route or report a
  surface. Routers remain coordinator-side authorities; focused skills remain
  leaf nodes; production-review skills remain surface synthesis nodes. Add a
  nested coordinator only when the user explicitly requests hierarchical graph
  execution and the subgraph can preserve the same manifest, journal, raw
  reports, and validation ledger without summarizing across the boundary.
- Do not mutate git state unless the user explicitly requests that operation.
- Make pre-dispatch and final user output self-contained. Do not rely on
  commentary or worker reports that the user cannot see.

Read [references/execution-feasibility.md](references/execution-feasibility.md),
[references/node-contract.md](references/node-contract.md), and
[references/report-contract.md](references/report-contract.md) before capture,
routing, or dispatch. Use their capability/deadline gate, scope manifest, worker
prompt, result schema, graph journal, and user-reporting rules verbatim.

## 0. Establish Execution Feasibility

1. Inspect the runtime's documented subagent lifecycle and capacity surfaces
   before repository capture or router loading. Do not create a dummy worker.
2. Accept only aggregate lifecycle metadata that cannot contain prior messages,
   findings, reports, outputs, or conclusions. If the available mechanism can
   expose task context, do not call it for capacity diagnosis; if it leaks
   unexpectedly, record an isolation failure and block.
3. Require authoritative support for fresh no-inherited-turn workers and at
   least one free concurrent worker slot. Do not require a lifetime creation
   count. When the runtime supplies an authoritative count and lifecycle
   semantics, preserve them as a completion forecast; only a known zero blocks
   the first dispatch.
4. Require at least one feasible first worker before performing expensive scope
   capture or routing. On failure, use the concise blocked-capability report in
   `references/execution-feasibility.md`; claim zero focused skills or validators
   executed and do not construct a substitute same-context review.
5. Persist the safe aggregate evidence and gate result in the graph journal.

After building a provisional node plan, count every selected worker, retry,
validator, independent check, fix iteration reserve, revalidation, and synthesis
rerun for reporting. Recheck peak concurrency and the hard-deadline dispatch
window, but do not demand that an unavailable lifetime count or every worst-case
node cap fit before dispatch. State the incremental stop policy and preserve all
completed evidence if worker creation or the deadline later blocks the rest.

## 1. Capture The Review State

1. Read repository-local instructions and determine whether the request
   authorizes review only or review and fixes.
2. Establish branch, staged-only, changed-worktree, pull-request, release, or
   whole-repository scope. Default to branch scope.
3. Run `scripts/capture_scope.py` with the matching capture mode and one
   repeatable `--path` argument for every explicit user scope boundary. Map
   pull-request and release scope to `branch`; use `baseline` only for
   whole-repository scope. For branch capture, pass the explicit or inferred
   base when known. Retain its JSON as the captured scope manifest shared by
   every worker.
4. Initialize the graph journal from `references/report-contract.md`. Record the
   user request, applicable nested instruction files, exact diff or inventory
   commands, and any external limitations alongside the manifest.
5. Recompute `scope_fingerprint`, `captured_worktree_fingerprint`, and the
   repository-wide content-based `repository_state_fingerprint` before accepting
   each node result. If any changed unexpectedly, stop dispatch, mark completed
   evidence stale, recapture scope, and replan.

Use the repository Python policy when running the helper, normally:

```sh
uv run python <review-graph-dir>/scripts/capture_scope.py --repo <repo> --mode branch --base <base> --path <path>
```

In staged mode, `scope_fingerprint` identifies the selected index state and
`captured_worktree_fingerprint` identifies the current files validators would
execute. `repository_state_fingerprint` covers HEAD, branch, index, every tracked
worktree file, and every nonignored untracked file even outside a path-bounded
review. Require audit workers to inspect the staged diff as authoritative. Key
semantic findings to the staged fingerprint and runtime validators to the
worktree plus repository-state fingerprints.

## 2. Build The Graph

Use the existing orchestrator routing matrices as coordinator-side selection
authorities, not executable graph nodes. Read each applicable
`references/check-routing.md` completely. While an orchestrator `SKILL.md`
contains unique scope or selection rules not yet present in its routing
reference, read it as a supplemental contract but never execute its grouped
review loop. Record each authority as `consulted`, never `run`, and preserve
every selected and meaningfully skipped leaf with its routing reason in the
graph journal.

Treat `repo-review` and the language/documentation orchestrators as entrypoint
front ends. An entrypoint may normalize user scope and select a routing matrix,
then hand execution to `review-graph` once. After that handoff, this graph owns
capture, leaf selection, isolated dispatch, validation, synthesis, and final
reconciliation. Do not invoke an entrypoint's orchestration loop from inside the
graph or allow it to delegate recursively back into the active graph.
Accept only task inputs in that handoff: original request, repository root,
authorization, scope mode/base/path boundaries, applicable surface hints,
instruction paths, and hard deadline. Do not accept findings or claimed review
completion from the entrypoint.

| Surface | Routing authorities |
| --- | --- |
| Repository | `../repo-review/SKILL.md`, `../repo-review/references/check-routing.md` |
| C++ | `../cpp-review-orchestrator/SKILL.md`, `../cpp-review-orchestrator/references/check-routing.md` |
| Rust | `../rust-review-orchestrator/SKILL.md`, `../rust-review-orchestrator/references/check-routing.md` |
| Python | `../python-review-orchestrator/SKILL.md`, `../python-review-orchestrator/references/check-routing.md` |
| Documentation | `../docs-review-orchestrator/SKILL.md`, `../docs-review-orchestrator/references/check-routing.md` |

Load every applicable static repository reference selected by a routing
authority, such as `rust-review-orchestrator/references/la-stack.md`. Attach its
absolute path to each affected isolated leaf and synthesis node so fresh workers
receive the same domain constraints as a manual orchestrator run. Static routing
or repository guidance is allowed; predecessor findings, conclusions, and prior
worker reports are not.

Treat `project-tooling-review` as a leaf worker. Treat every focused C++, Rust,
Python, and documentation skill selected by a routing authority as a leaf
worker. Deduplicate a leaf selected by more than one surface and record every
owner that will reuse its evidence.

Inventory Python source, tests, and `pyproject.toml` packaging signals even when
they live under a skill, plugin, documentation, or repository-support directory.
Keep the Python router authoritative, but apply the narrow graph-side guard in
`scripts/review_graph_plan.py`: package mode, build metadata, installed modules,
or console entry points require `python-build-portability`. If the router omitted
it, add the leaf with the observed signal and record that guard separately from
the router's normal matrix.

Create an explicit node plan containing:

- stable node ID and exact skill ID
- absolute `SKILL.md` path
- reason selected or skipped
- node-owned scope paths plus captured scope, worktree, and repository-state
  fingerprints
- applicable instruction files and static routing/repository reference paths
- predecessor node IDs
- mode: `audit`, `validation`, `independent-review`, `synthesis`, `fix`, or
  `revalidation`
- expected validators or reusable validation-ledger entries
- elapsed-time and retry budgets
- maximum fresh-worker attempts, including retries and post-fix reruns

Order tooling before language nodes when command or validator semantics changed.
Order documentation after source owners when it depends on implementation
truth. Add the applicable `cpp-production-review`, `rust-production-review`, or
`python-production-review` synthesis node after that language's specialist
nodes. Do not dispatch synthesis nodes in the initial specialist wave.

Derive explicit validation requirements from routing guidance, specialist
reports, fixes, and invalidation events. Deduplicate them by source state,
command, built or installed artifact, environment, configuration,
instrumentation, and exact selection. Create one `review-validator` node per
independent validation unit and pass any matching ledger evidence; the node must
return `reused` or execute the uncovered commands.

Before deduplication, ingest every user-supplied standalone Validation Result:

1. Preserve the complete result and validate it against
   `review-validator/references/result-contract.md`.
2. Recompute the graph's three fingerprints. Mark the evidence stale when any
   identity differs; do not reuse it against a merely similar scope.
3. Match exact requirement, command, working directory, environment,
   configuration, instrumentation, artifact or installation target, and test
   selection. A portable ledger export is an index into the complete result,
   not a substitute for those fields.
4. Add matching `passed` or `reused` evidence to the candidate validation
   ledger. Still dispatch the owning graph `review-validator` node so it can
   verify the entry and return `reused` under the current graph manifest.
5. Preserve `failed`, `blocked`, or `not-applicable` results as evidence only.
   Route raw failure evidence to the owning reviewer for diagnosis and never
   convert it to P0-P3 without a review finding. A not-applicable import does not
   satisfy a graph-derived requirement.
6. Record accepted, stale, malformed, and evidence-only imports in the graph
   journal and expose their disposition in the pre-dispatch and final reports.

For a concrete change target, add one independent `review-agent` node after the
current specialist and validation nodes but before final surface synthesis. The
dependency controls order only: do not pass predecessor conclusions to the
independent reviewer. Route its findings to the applicable surface synthesis and
finding ledger. For review-and-fix work, rerun this node against the final
post-fix change before the final synthesis.

Before presenting the graph, apply the schedule assessment from
`references/execution-feasibility.md`. Record planned fresh creation attempts,
optional lifetime creations remaining, the full-plan completion forecast, peak
and free concurrent slots, full-cap critical path, final-reconciliation reserve,
hard deadline or `unbounded by request`, and the stop policy. A full-cap path
longer than the deadline is a visible completion risk, not a reason to pre-block
an otherwise runnable graph.

Before execution, show the compact plan and meaningful skips to the user.
Use the pre-dispatch format in `references/report-contract.md`; include the
routers consulted separately from the skills that will actually run.

## 3. Dispatch Leaf Workers

For each ready node:

1. Recheck all three captured fingerprints.
2. Select the mode-specific worker prompt from `references/node-contract.md`.
   Pass only its raw task-local inputs. A focused review receives repository
   path, instructions, scope manifest, exact skill path, authorization, and
   prior validator evidence. A validator receives an exact validation dispatch.
   An independent reviewer receives only the concrete change target, scope
   identity, instructions, and its exact skill path.
3. Recompute the time remaining before every dispatch. Reserve enough time for
   final reconciliation and cap the node timeout to the smaller of its own cap
   and the remaining dispatch window. Journal the creation attempt, then spawn a
   fresh worker with no inherited turns and wait for that worker before
   dispatching the next node. Record creation success separately from skill
   loading and result acceptance.
4. Independently rerun the coordinator's state-verification command before
   accepting the report. For a read-only node, require all three identities to
   remain unchanged. For a fix node, recapture state and require every changed
   path to appear in its exact change records while HEAD, branch, and index
   remain unchanged.
5. Preserve the result unchanged and validate it against the result contract.
6. Add new validator evidence to the shared ledger only when the report names
   the exact command, applicable scope, worktree, and repository-state
   fingerprints, environment or configuration, and result.
7. Append the accepted result and its plain-language outcome to the graph
   journal without shortening or silently merging its findings.

If creation fails, record the node as `blocked-before-execution`; do not claim
its skill loaded or executed. Preserve every completed raw report and block
every undispatched node rather than reusing an earlier worker or substituting
coordinator review. List each planned validator prevented by the failure as
`not-run`, preserving its exact command plan.

When the hard deadline leaves no dispatch window, interrupt an active worker if
needed, preserve its returned or blocked evidence, and mark every undispatched
node `blocked-before-execution` with `global-deadline-exhausted`. Keep their
selection reasons and planned validator commands in the journal and final
report. Do not silently narrow the graph to nodes that happened to finish.

Do not tell workers the expected findings, the coordinator's diagnosis, or
another worker's conclusions. Supply prior reports only to a synthesis, fix, or
revalidation node whose contract requires them.

## 4. Enforce The Node Gate

Apply the mode-specific acceptance rules in `references/node-contract.md`.
Review and independent-review nodes accept `completed`, `no-findings`, or
`blocked`. Validation nodes accept `passed`, `failed`, `reused`, `blocked`, or
`not-applicable`.
Require the reported skill ID and expected fingerprint identities to match the
dispatch. Apply status-sensitive rules to observed state: successful read-only
nodes must match all three before and after, while blocked nodes must preserve
the exact observed mismatch or unavailable check.

When a node exceeds its budget, request one compact status. If it does not
return promptly, interrupt it and mark the node blocked. Retry a timeout only
when the worker identified a transient cause or the user authorizes a longer
budget.

If a result is malformed, send one formatting-only follow-up to the same worker.
If evidence shows that the skill was not actually loaded or the requested scope
was not inspected, discard the result and retry once in a new fresh worker.
After the retry, mark the node blocked rather than synthesizing around it.

Do not begin surface synthesis until every specialist, validation, and
independent-review predecessor is accepted or explicitly blocked.

## 5. Run Surface Synthesis

Dispatch each language production-review skill as its own fresh synthesis node.
Give it the complete accepted specialist reports, applicable independent-review
findings, meaningful skips, shared validation ledger, and current scope
fingerprint. Require orchestrated mode and prohibit it from rerunning completed
specialist analysis or validation. Require it to account for every predecessor
report in the `Predecessor Coverage` section of the node result.

For tooling and documentation, reconcile accepted leaf reports in the
coordinator without introducing new findings. Preserve ownership, disagreements,
and blocked evidence for the final repository synthesis.

## 6. Apply Fixes Only When Requested

Complete the read-only audit graph before editing. Then:

1. Assign every accepted finding to one owning skill.
2. Dispatch fresh fix workers sequentially, each with exactly one skill, its raw
   audit report, current scope manifest, and explicit fix authorization.
3. Require the fix worker to use the node result contract, list changed files,
   identify every addressed finding, explain what changed and why for each
   change record, and declare invalidated or newly required validation. Accept
   conforming focused evidence it produced, but dispatch `review-validator` for
   every uncovered requirement. A material change without an owning finding
   must receive an explicit incidental-change ID and rationale.
4. Recapture all three fingerprints after every fix. If the original graph was
   staged-only, transition fixes and revalidation to a path-bounded worktree
   manifest because source edits do not alter the Git index.
5. Mark any earlier node whose owned files, assumptions, scientific behavior,
   public contract, tests, or validator state changed as invalidated.
6. Dispatch the required validation nodes, then fresh revalidation nodes for all
   invalidated owners. Do not rely on the fix worker's self-review as
   independent revalidation.
7. For a concrete change target, rerun `review-agent` without predecessor
   conclusions after post-fix validation and revalidation.
8. If validation failed or the independent reviewer found a new actionable
   defect, route the raw evidence to its focused owner. Do not convert a failed
   command into a finding without diagnosis. When fixes remain authorized and
   safe, return to step 2 and repeat fixing, recapture, validation,
   revalidation, and independent review. Stop only when the gates converge or a
   recorded blocker or retry budget prevents another iteration.
9. Invalidate and rerun every surface synthesis whose predecessor evidence
   changed. Final explanations must come from current post-fix evidence, not the
   pre-fix synthesis.

Never allow concurrent workers to edit the shared worktree.

## 7. Finish With Graph Evidence

Require this invariant before reporting completion:

```text
selected nodes = accepted nodes + blocked-after-execution + blocked-before-execution
worker creation attempts = workers created + creation failures
planned validators = executed validators + validators not run
canonical findings = fixed + remaining + accepted-risk + blocked
material changes = finding-linked changes + explicit incidental changes
validation requirements = passed + reused + failed + blocked
```

Use the final format and reconciliation gates in
`references/report-contract.md`. Lead with blockers and unresolved high-severity
findings, but always include the complete skills-run table, finding disposition
ledger, change-and-rationale ledger, meaningful skips, non-overlapping
validation ledger, `Review Graph Evidence` table, stale evidence, and git-state
status. State explicitly that no same-context substitute was used for any
blocked node.
