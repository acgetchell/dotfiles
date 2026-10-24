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

## Assess Decisions and Actions

Evaluate the emitted plan and actual tool actions, not keyword matches:

| Check | Observable pass condition |
| --- | --- |
| Availability | A merged unpublished prerequisite does not permit normal consumer adoption or removal of its working adapter |
| Ownership | Upstream publication uses upstream fixtures/gates and can finish with real adoption still open |
| Scope | Mandatory, partial, and deferred work and a publication cutoff are explicit; broad issues remain open for unmet acceptance |
| Mapping | Every step, PR, checkpoint, publication, and adoption stage names its owner and exact issues or a concrete unfiled tracker proposal |
| Batching judgment | Costs and delivery consequences justify the chosen grouping; changed readiness/deadlines can change that decision |
| Existing decisions | Current capstones and native metadata are represented accurately; scope changes remain explicit proposals |
| Evidence | Validation owners and source/context/platform/artifact identity remain distinct; exact-commit fallback and approval checks survive |
| Cost | Reported hours are not converted into invented speedups; elapsed and runner costs are distinguished |
| Boundary | No unauthorized mutations, live CI, benchmark runs, or publication occur |
| Actionability | The next item and the published release that unlocks each consumer follow-up are concrete |

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
