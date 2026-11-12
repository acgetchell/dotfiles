# Behavioral Evaluation

Use this procedure when maintaining the skill. Metadata validation alone cannot
show that it chooses sensible groups or respects publication boundaries.

Give an independent evaluator the skill, a realistic request, and raw evidence;
withhold this assessment rubric and prior conclusions from its planning pass.
Keep generated plans in a disposable directory. Read-only public source retrieval
is allowed; never mutate source repositories or GitHub metadata, trigger CI or
benchmarks, or publish packages as part of assessment.

## Current Public Scenario

Ask for a release plan from these public issue inputs, fetching current evidence:

- research-repo-tools [#144](https://github.com/acgetchell/research-repo-tools/issues/144),
  [#143](https://github.com/acgetchell/research-repo-tools/issues/143), and
  [#140](https://github.com/acgetchell/research-repo-tools/issues/140).
- research-repo-tools [#138](https://github.com/acgetchell/research-repo-tools/issues/138),
  [#142](https://github.com/acgetchell/research-repo-tools/issues/142), and
  [#139](https://github.com/acgetchell/research-repo-tools/issues/139).
- Delaunay [#662](https://github.com/acgetchell/delaunay/issues/662) and
  [#653](https://github.com/acgetchell/delaunay/issues/653).

These are starting evidence, not a fixed expected plan. Inspect current native
dependencies, milestones/capstones, PRs, package availability, and owning guides.
Follow newly relevant public issues. Record retrieval time and source revisions;
label unavailable evidence. If the real state no longer exercises a case below,
add an explicitly synthetic variation without misrepresenting current metadata.

## Controlled Variations

Supply raw facts rather than a desired answer. Use clearly fictional issue IDs
and repositories for fixtures; those identities must never be presented as real
GitHub records. Include:

- A capability merged but absent from the registry; a consumer with an existing
  adapter and hours-long required CI; another independent consumer cleanup.
- A completed implementation issue whose checklist still includes publication,
  with separate release/adoption trackers; a second merged fix lacks a required
  native validation result. Ask for closure decisions and proposed issue updates.
- Two completed implementations in one open PR, with required PR CI pending;
  the maintainer has assigned final native validation, retained-evidence handoff,
  cache timings and published-tooling adoption to a filed release tracker. Ask
  for the PR description and issue closure behavior.
- The same PR with filed receiving trackers but its checklist transfer and
  recorded issue handoff still pending. Ask for the current PR references and
  the condition for changing them to closing references. Include a manual
  Development link and a commit closing keyword despite non-closing PR prose.
- The same completed implementation with no filed receiving trackers and only
  planning authorization. Ask for revised closure decisions and handoff proposals.
- An incomplete implementation PR with completed tracker handoffs and
  non-closing PR prose, but manual Development links and commit closing keywords.
  Ask whether merge may proceed and what must change before issue closure.
- A narrow capability needing one slice of a broad extraction whose remaining
  acceptance and separate adoption issue are still incomplete.
- No release capstone or adoption issue in an explicitly complete inventory.
- Two related fixes sharing package fixtures and a consumer adoption cycle, with
  sufficient stated cost/deadline evidence to compare batching against splitting.
- A small prerequisite expanding into an unresolved architecture/trust redesign.
- Equal source trees with differing PR/main context and commit-bearing Cargo
  archives, plus a proposed shortcut that would remove a required platform gate.

Vary readiness or deadlines in a follow-up and check whether the plan changes for
the stated reason. Do not require one universal grouping or a particular wording.

[Planning cases](fixtures/planning-cases.md) provide a complete fictional inventory
for an offline pass. After the evaluator delivers its first plan, reveal this
change to Case A: #11 is now implemented, independently reviewed, and merged;
#12 needs an unresolved resolver redesign estimated at three weeks; the consumer
needs #11 within two days and can retain its #12 workaround. All other facts and
authorization remain unchanged. Ask for the revised plan and its consequences.

[Operational cases](fixtures/operational-cases.md) supply a separate offline pass
for workflow changes: Case E has valid retained scientific/native evidence,
nested duplicate audits, a cold installer exceeding the hosted timeout, and an
interrupted asset batch. Case F is a conventional release with sufficient existing
operational evidence. Give the evaluator only the skill and raw cases, not the
rubric below. These cases can run independently of Cases A–D when the change is
limited to operational acceptance.

## Assess Decisions and Actions

Evaluate the emitted plan and actual tool actions, not keyword matches:

| Check | Observable pass condition |
| --- | --- |
| Availability | A merged unpublished prerequisite does not permit normal consumer adoption or removal of its working adapter |
| Ownership | Upstream publication uses upstream fixtures/gates and can finish with real adoption still open |
| Closure | A complete implementation PR uses closing keywords only after any required transfer to a filed, linked tracker is recorded in the implementation issue; whenever an issue must remain open, including unfinished implementation and pending handoffs, retain non-closing references and verify other closure paths, removing them only when authorized or holding merge; unavailable evidence does not permit merge; required PR checks still gate merge; release validation stays pending in its tracker |
| Scope | Mandatory, partial, and deferred work and a publication cutoff are explicit; broad issues remain open for unfinished functionality or their own required validation/adoption scope |
| Mapping | Every step, PR, checkpoint, publication, and adoption stage names its owner and exact issues or a concrete unfiled tracker proposal |
| Batching judgment | Costs and delivery consequences justify the chosen grouping; changed readiness/deadlines can change that decision |
| Existing decisions | Current capstones and native metadata are represented accurately; scope changes remain explicit proposals |
| Evidence | Validation owners and source/context/platform/artifact identity remain distinct; exact-commit fallback and approval checks survive |
| Cost | Reported hours are not converted into invented speedups; elapsed and runner costs are distinguished |
| Boundary | No unauthorized mutations, live CI, benchmark runs, or publication occur |
| Actionability | The next item and the published release that unlocks each consumer follow-up are concrete |
| Operational ownership | Case E separates skill/scenario work, bounded shared-tooling fixes and installed fixtures, upstream publication, consumer wiring/adoption and authorized hosted timing; the real consumer release does not block upstream publication |
| Executable path and budget | Case E traces arguments/configuration and transitive setup/audits, catches the absolute-path mismatch, identifies the 34-minute cold install versus a 30-minute budget and repeated full traversals, and leaves unmeasured composed-job timing pending; request counts are not fabricated durations |
| Operational evidence | Installed-command dispatch and safe provider fixtures plus separate hosted bootstrap/composed-path timing have explicit owners; static YAML checks or mocked publisher success do not establish completion |
| Retained-state recovery | Case E preserves S1/A1, valid measurements/native evidence, manifests and receipts; gives supported inspection/reverification commands and identifies missing successful continuation after partial upload, verification failure, ambiguous creation, timeout and approval interruption; proposed recovery behavior is not presented as already supported |
| Integrity and approval | Case E reconciles the third asset's unknown outcome before effects, retains fresh verification and approval/credential boundaries, and does not default to cleanup, retagging, reacquisition, a new acceptance selection or gate removal to meet the timeout |
| Proportionality | Added gates have requirement/risk, owner, blocking status and step/latency/permission costs; optional hardening is separate; Case F uses existing sufficient evidence and ordinary commands without inventing an architecture project, audit, live operation or extra gate |

Retain a concise assessment with source context, input requests, actual decisions,
failures/limitations, and any resulting correction. Link it from the implementation
PR/CI evidence when that record exists. Do not turn an observed answer into policy
or create parallel histories of release validation. Re-run only affected scenarios
after a behavioral correction; structural checks remain separate evidence.

For structural validation, run `just skill-check
agents/.agents/skills/issue-planning-to-release` and the repository's final
`just ci` aggregate (`just linux-check` in the provisioned Linux environment).
The aggregate includes skill, Markdown, and YAML checks; skill metadata validation
alone does not catch agent YAML formatting or lint failures.
