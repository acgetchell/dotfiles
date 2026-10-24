# Issue Planning to Release: Behavioral Evaluation

The [issue-planning-to-release skill](../agents/.agents/skills/issue-planning-to-release/SKILL.md)
was evaluated on 2026-10-24 for [dotfiles #230](https://github.com/acgetchell/dotfiles/issues/230).
The inspected plans passed the public scenario, three controlled cases, and a
changed-readiness follow-up. No behavioral repair was needed after these runs.
This is evidence about planning decisions, not validation of the proposed upstream
implementations or releases.

The [retained evaluation record](evidence/issue-planning-to-release-2026-10-24.json)
contains the requests, complete emitted plans, evaluated skill-file hashes,
source context, observed decisions, assessment, and limitations. The
[evaluation procedure](../agents/.agents/skills/issue-planning-to-release/references/behavioral-evaluation.md)
and [fictional input cases](../agents/.agents/skills/issue-planning-to-release/references/fixtures/planning-cases.md)
support future assessment without treating these answers as permanent policy.

## Method and boundaries

Two independent Astra planner contexts received the skill and raw evidence,
without the implementing agent's conversation, implementation diff, assessment
rubric, or expected groupings. One used current public sources; the other used a
complete fictional inventory. After the fictional planner delivered its first
plan, it received a changed-readiness request. The implementing agent inspected
the resulting decisions, issue mappings, ownership, evidence requirements, and
action boundaries.

Public retrieval was read-only. Generated plans and source responses were isolated
in a temporary directory. The evaluators did not alter source repositories or
GitHub metadata, install packages, trigger CI or benchmarks, or publish anything.
Only the selected evaluation record and this assessment were retained in dotfiles.

## Current public scenario

The request started with research-repo-tools
[#144](https://github.com/acgetchell/research-repo-tools/issues/144),
[#143](https://github.com/acgetchell/research-repo-tools/issues/143),
[#140](https://github.com/acgetchell/research-repo-tools/issues/140),
[#138](https://github.com/acgetchell/research-repo-tools/issues/138),
[#142](https://github.com/acgetchell/research-repo-tools/issues/142), and
[#139](https://github.com/acgetchell/research-repo-tools/issues/139), plus Delaunay
[#662](https://github.com/acgetchell/delaunay/issues/662) and
[#653](https://github.com/acgetchell/delaunay/issues/653).

| Evidence | Observed context |
| --- | --- |
| Upstream source and guides | [research-repo-tools `4085125526e21b2855eb7c61a52ee312782ae31a`](https://github.com/acgetchell/research-repo-tools/commit/4085125526e21b2855eb7c61a52ee312782ae31a) |
| Consumer source and guides | [delaunay `e365c531ea157469c0f8767153e75d0ac6db920e`](https://github.com/acgetchell/delaunay/commit/e365c531ea157469c0f8767153e75d0ac6db920e) |
| Current scope decision | [#146](https://github.com/acgetchell/research-repo-tools/issues/146) and [milestone 10](https://github.com/acgetchell/research-repo-tools/milestone/10) already specified a comprehensive v0.2.4: #125–#144 plus #145 documentation |
| Availability | [PyPI project metadata](https://pypi.org/pypi/research-repo-tools/json) showed 0.2.3; [exact 0.2.4 metadata](https://pypi.org/pypi/research-repo-tools/0.2.4/json) returned 404. Delaunay's manifest/lock used registry 0.2.3. No fresh installation was performed. |
| Native blockers | #662 depended on upstream #144; #653 depended on #140/#129/#130. The six starting upstream issues had no recorded blockers. |
| Existing CI costs | [Delaunay run 40067665950, attempt 1](https://github.com/acgetchell/delaunay/actions/runs/40067665950) supplied one complete four-job timestamp sample; no run was triggered. |

Current metadata made a missing-release-tracker test inappropriate for this public
case: #146 already existed. The planner preserved its eight implementation groups,
separate #145 documentation PR, and release-preparation PR: ten upstream PRs and
one publication. It did not force the original seed issues into a smaller release
or treat the intended review order as a fabricated native blocking chain.

| Decision examined | Observed outcome |
| --- | --- |
| Partial extraction | G1 contributes #140's core evidence/asset work; G8 completes its remaining upstream interfaces/migrations. #140 stays open after G1. |
| Coherent batching | #138/#142 share resolver/transaction work; #139 joins their update/audit contract. Independent groups retain their review boundaries. |
| Publication cutoff | #146 waits for its agreed scope and upstream gates, then verified PyPI publication. It does not wait for Delaunay or la-stack adoption. |
| Separate adoption | Delaunay #662 can inventory/clean up independently; cross-commit reuse waits for published #144 and normal pins/locks. #653 retains its broader extraction/adoption acceptance. |
| Issue mapping | PR groups, decision checkpoints, publication stages, validation ownership, and consumer follow-ups identify the owning repository and exact issues. Existing trackers are reused. |
| Architectural growth | #140/#144 and other uncertain prerequisites receive bounded checkpoints and explicit scope decisions; exact-commit fallback does not count as successful reuse implementation. |
| Evidence integrity | Equal trees do not establish execution-context or Cargo-archive equivalence. Native coverage, trusted run/attempt/artifact identity, approval revalidation, and findings/report gates remain required. |
| Next action | Start G1's public evidence contract and acceptance fixtures under #128/#140/#143/#144, coordinated by #146; identify verified PyPI v0.2.4 as the actual consumer unlock. |

The planner distinguished **6h 17m 55s aggregate job occupancy** from
**2h 57m 32s elapsed** for the sampled Delaunay run. Those totals were independently
recomputed from the four saved job records: 22,675 runner-seconds and 10,652 elapsed
seconds. They describe one existing run, not future savings, billing costs, or a
per-validator breakdown. Unknown design, review, publication and adoption costs
remained explicit.

The retained record also includes the selected GitHub step names, numbers, and
UTC start/end timestamps behind the public plan's setup and validation columns.
They were added during PR #231 review from the same existing run/attempt, with
the source endpoint and retention time recorded separately from the original
evaluation. Setup and validation durations can therefore be recomputed without
depending on the continued availability of GitHub's job records; other job steps
are explicitly outside that retained subset.

## Controlled cases and changed evidence

The fictional inventories supplied missing trackers and states that the current
public repositories did not necessarily exhibit. Their costs are test inputs,
not measurements of real projects.

| Case | Actual planning decision | Assessment |
| --- | --- | --- |
| A: related fixes ready about two hours apart; costly shared release/adoption cycle; next-week deadline | One #11/#12 implementation group and publication, defer unrelated #13, then adopt through consumer #51. Propose an unfiled release capstone. | Batching follows shared contract, readiness and stated cost; no default release per issue. |
| B: #31 selection slice merged, registry still lacks it, broad #30 incomplete, no release/adoption tracker | Publish the coherent #31 slice after outstanding upstream gates; leave #30 open; propose concrete unfiled release and adoption issues. Keep the working consumer adapter and independent #70 inventory. | Merge is not availability; partial upstream work does not close broad acceptance; consumer CI does not block upstream publication. |
| C: reuse prerequisite becomes unsettled trust design; PR/main context differs, Windows is missing, archive embeds the wrong commit | Ship independent diagnostics #42 under existing gates; bound the #41 investigation; reject the proposed shortcut and retain exact-release validation/artifact/approval requirements. | Preserves successful independent delivery and required evidence without treating fallback as implementation of reuse. |
| A follow-up: #11 merged/reviewed, #12 now a three-week redesign, #11 needed within two days | Reverse the batching decision: publish #11 separately, adopt part of #51 while retaining the #12 workaround and leaving #51 open; give #12 a later checkpoint, release and adoption cycle. | Grouping responds to changed delivery evidence. Extra publication/adoption cost is acknowledged rather than hidden or used to justify missing the deadline. |

The follow-up explicitly distinguished no new #11 implementation PR from a new
partial consumer PR and later #12 implementation/adoption PRs. Publication and
investigation phases were not automatically counted as additional PRs. Exact
versions, final evidence, and future success were not invented.

## Structural validation and limits

Behavioral assessment is separate from structural validation. The focused skill
check is `just skill-check agents/.agents/skills/issue-planning-to-release`;
final validation uses `just ci` (`just linux-check` in the provisioned Linux
environment), which includes `just check-skills`, `just markdown-check`, and
`just yaml-check`. Skill metadata validation alone does not establish that agent
YAML passes formatting and lint checks. Local reference checks and Stow
verification additionally check that the skill and its references are reachable.

These are model-generated plans assessed by the implementing agent, not human
consensus or a statistical benchmark. Both independent contexts used Astra and
can share biases. Surrounding GitHub/Rust skill integration was inspected locally;
it did not receive a separate Rust release-train behavioral run. Native metadata
can change, and future assessment must fetch current evidence. The evaluation
does not establish that any proposed implementation, package installation,
consumer integration, or release would succeed.
