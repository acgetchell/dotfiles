# TypeSafe Shadow Routing Evaluation

**Current disposition:** production adoption was declined and
[#74](https://github.com/acgetchell/dotfiles/issues/74) is closed as not planned.
The opt-in harness and records are retained for a future pinned revision under
[#75](https://github.com/acgetchell/dotfiles/issues/75). The upstream agent skill
is no longer vendored here. The cases below are historical regression and
development data; a new adoption decision requires fresh held-out evidence.

This records the bounded follow-up to [issue #73](https://github.com/acgetchell/dotfiles/issues/73)
and [PR #94](https://github.com/acgetchell/dotfiles/pull/94), evaluated on
2026-10-03 after the graph overhead fixes in #87 and #89 merged.
The disposition after the repeat is **retain shadow mode**. All seven approved
live requests succeeded without retries, at an estimated API cost of $0.00289254.
Jev selected all 21 independently labeled applicable concerns and 17 labeled
unnecessary concerns. Reporting, failure handling, offline fixtures, budget
controls, independent labels, response replay, and the bounded routing repeat
are complete. Historical proof recovery and total review cost remain qualified
as described below.

The [supporting records](evidence/typesafe-shadow-2026-10-03.json) retain source
and request identities, original response judgments, labels and their reasons,
fresh selector decisions, measurements, and limitations. The
[evaluation fixture](../agents/.agents/skills/review-graph/scripts/fixtures/routing_evaluation.json)
contains the two original real scopes and five supplemental synthetic scopes.
No production routing, required coverage, or proof-acceptance behavior changes.

The subsequent [threshold evaluation](typesafe-threshold-evaluation.md) treats
these seven cases as development data and evaluates a frozen 0.70 cutoff with
coordinator assessment from 0.50 on eight new scopes. Its findings and evidence
are separate from this first phase.

## Corrected original replay

The primary report now selects every candidate with probability at least 0.5,
the original pilot cutoff. It prints selected IDs and disagreements. The 0.2/0.8
bands remain descriptive and separate. Failed, stale, partial, or incomplete
evidence leaves decisions unknown, including threshold sweeps.

Both retained requests replayed without a new API request. This replay changes
reporting only; it is not a new observation of Jev or downstream review work.

| Original scope | Baseline selections | Jev selections | Disagreements |
| --- | ---: | ---: | ---: |
| la-stack #261 | 4 | 6 | 2 |
| markov-chain-monte-carlo #187 | 11 | 14 | 5 |

For la-stack, Jev added `python.build` and `python.cli`. For MCMC, Jev added
`cpp.scientific`, `python.scientific`, `docs.repository`, and
`rust.borrowed-views`, while omitting baseline-selected `rust.prelude`.
Each request asked all 45 catalog leaves, allowing multiple selections.

Fresh independent model reviewers labeled every candidate without seeing the
baseline or Jev answers. Applying their current ownership judgments
retrospectively gives the following counts:

| Scope and original method | Applicable selected | Applicable missed | Unnecessary selected |
| --- | ---: | ---: | ---: |
| la-stack baseline | 4 | 0 | 0 |
| la-stack Jev | 4 | 0 | 2 |
| MCMC baseline | 9 | 0 | 2 |
| MCMC Jev | 9 | 0 | 5 |

These are disagreements relative to independent model labels, not human
consensus, held-out accuracy, or findings about code correctness. Shared model
bias and subjective specialist ownership remain limitations. No prompt or
threshold tuning was performed in this first phase, and no calibration claim
is made.

Risk-category counts and every label rationale are retained in
`retrospective_independent_assessment.by_risk`. Neither original method missed
a labeled applicable concern in these two cases. Jev's extra la-stack selections
fall in boundary and tooling categories. Its MCMC extras fall in numerical,
documentation, ownership, and other categories. Categories may overlap and are
not defect severities.

## Original evidence recovery and limits

The la-stack packet, baseline, request, and result were recovered from retained
chat output and Git objects and verified against their original digests. The
MCMC request digest also matches the original; its probabilities were recovered
from the printed six-decimal table. The original full MCMC packet and response
digests are unavailable, so that recovery cannot establish original response
byte identity. These limitations remain attached to the exported records.

Public exports replace machine-local metadata paths with placeholders and have
their own packet digests. Request content and request digests remain unchanged.
Both exported packet/result pairs passed the normal replay verifier.

The original la-stack paired review reported complete proofs, passed validation,
and `not-ready` code readiness for both arms. The TypeSafe arm's two extra
specialists produced no unique finding. The retained receipts report 18 distinct
workers, including common/recovery work, and a combined observed span through
proof publication of 2,196.33 seconds. The two arms shared resources and validation;
that span is not the runtime of either arm in isolation. Arm-specific materialized
worker inputs were 146,843 and 192,463 bytes, respectively, not provider tokens.

Full downstream proof artifacts are no longer present at their recorded temporary
paths; the cause is unknown. Retained status receipts and original file hashes
are included, but absent files cannot be reverified from hashes alone. Historical
proof completion is therefore a reported observation, not a newly verified proof.
No replacement proof was generated to conceal this archival gap.

| Original routing call | Reported input tokens | Reported output tokens | API elapsed seconds | Estimated API dollars |
| --- | ---: | ---: | ---: | ---: |
| la-stack #261 | 15,127 | 836 | 0.264245 | 0.000635334 |
| MCMC #187 | 15,911 | 836 | 0.237204 | 0.000668262 |

These estimates use the dated published rate of $0.042 per million input tokens
and free output. Coordinator and worker token counts and dollar costs were
unavailable. Routing workflow time and API latency have different boundaries;
neither their ratio nor these API costs establish total review savings.

## Live repeat and independent labels

The repeat freezes the original source scopes while using the current catalog
and fresh ordinary selector decisions. Source commits are
`1572957a4ada1f8fba900ac18f9378e9e0366ba0` for la-stack and
`c77a21718db383cd60d11ae32443cbc6eaf123d1` for MCMC. The dotfiles base is
`e72e44ece253be66350d7b11b793c2b023c1e4f3`; the manifest also records the
modified adapter digest. Catalog and ownership instructions have changed since
the pilot, so new results would not isolate model variability alone.

Both methods received the same frozen source and dependency evidence. The
ordinary selector also consulted graph guidance, routing projections, ownership
references, and four focused skill bodies; those reads are itemized in the
supporting baseline record. Jev received the catalog's skill names and semantic
triggers in the unchanged Noul question template, without those full skill bodies.
The source comparison is controlled; total instruction context is not identical.

The fresh selector chose four leaves for la-stack and six for MCMC before any
repeat inference. Independent labels identify four and nine applicable leaves.
The MCMC difference is `rust.parse`, `rust.errors`, and `rust.simplification`;
it is a recorded ownership disagreement, not an independently proven selector
failure. Baseline reasons and labeled risk categories remain available for review.

The five supplemental scopes cover fixture generation, declarative tooling,
a nested diagnostic lockfile, a multi-surface validation claim, and a genuine
no-match case. Their independent labels contain eight positives, 214 negatives,
and three unresolved ownership decisions:

- `fixture-generator` / `python.tests`
- `declarative-tooling` / `rust.tests`
- `nested-diagnostic-lockfile` / `rust.build`

Unresolved labels are not scored as negative. Supplemental baselines remain their
original provisional decisions; only the two real scopes received fresh ordinary
selectors. Original provisional expected labels remain separately preserved.

The fresh real-scope selector presented five owned files totaling 30,972 bytes,
four dependency items totaling 14,739 bytes, and a 5,378-byte diff: 51,089 source,
excerpt, and diff bytes in all. Seven packet parse reads consumed 316,816 bytes
before decision freeze; two later bookkeeping reads consumed 90,422 bytes.
These are distinct byte measurements, not token estimates.

The selector recorded 25 CLI operations: nine for la-stack, six for MCMC, and ten
shared. Decision spans were 106.161 and 127.189 seconds, sequentially. The measured
span through both decisions was 258.658 seconds, and through artifact bookkeeping
505.452 seconds. Two initial setup operations preceded the timer, so full task time
is unknown. Selector model tokens, cached tokens, and dollar cost remain
unavailable. Selector work finished before the repeat Jev calls; the two methods
did not overlap.

The frozen live manifest permits seven requests, zero retries, and at most
448,000 input tokens, reserving $0.018816 against the $1 ceiling. Reservation uses
the published 64,000-token request maximum; it is not a tokenizer estimate.
Authentication succeeded through process-scoped credential injection. Following
direct approval, the runner submitted exactly the seven frozen payloads. Every
packet matched its prepared identity, every response returned `jev-1.13.0`, and
all 315 typed judgments were present. There were no failures, retries, or fallback
calls. No baseline decisions or independent labels were sent to Jev.

| Repeat scope | Jev selected | Applicable selected | Applicable missed | Unnecessary selected | Unresolved labels |
| --- | ---: | ---: | ---: | ---: | ---: |
| la-stack #261 | 6 | 4 | 0 | 2 | 0 |
| MCMC #187 | 15 | 9 | 0 | 6 | 0 |
| Fixture generator | 4 | 1 | 0 | 2 | 1 |
| Declarative tooling | 4 | 1 | 0 | 2 | 1 |
| Nested diagnostic lockfile | 2 | 1 | 0 | 1 | 1 |
| Multi-surface validation claim | 9 | 5 | 0 | 4 | 0 |
| No review skill match | 0 | 0 | 0 | 0 | 0 |
| Total | 40 | 21 | 0 | 17 | 3 |

Two of the 40 selections have unresolved expected labels; they are excluded from
the applicable/unnecessary counts. All 45 candidates in the no-match case were
left unselected. The fresh real-scope baseline selected 10 applicable concerns,
missed three MCMC concerns relative to the labels, and had no labeled unnecessary
selections. Jev included those three concerns but added eight labeled unnecessary
selections across the two real scopes. This tradeoff does not by itself show that
changing dispatches would improve a complete review.

The supplemental baselines are sparse: 197 labeled negative decisions and three
labeled positive decisions remain unknown, in addition to the three unresolved
expected labels. They cannot support a complete accuracy comparison with Jev.
Their omissions are retained as unknown rather than inferred negative decisions.

Per-case `by_risk` records retain coverage for every labeled category. Jev missed
no labeled applicable concern. Extra selections include boundary and tooling
ownership in la-stack; boundary, numerical, documentation, and ownership concerns
in MCMC; and command/application ownership, unrelated language surfaces, and
support-script ownership in the supplemental cases. These are applicability
judgments against the independent labels, not demonstrated defects.

| Repeat scope | Input tokens | Output tokens | API elapsed seconds | Estimated API dollars |
| --- | ---: | ---: | ---: | ---: |
| la-stack #261 | 15,151 | 836 | 0.298220 | 0.000636342 |
| MCMC #187 | 15,935 | 836 | 0.217865 | 0.000669270 |
| Fixture generator | 7,623 | 836 | 0.182139 | 0.000320166 |
| Declarative tooling | 7,536 | 836 | 0.308236 | 0.000316512 |
| Nested diagnostic lockfile | 7,566 | 836 | 0.143748 | 0.000317772 |
| Multi-surface validation claim | 7,560 | 836 | 0.165910 | 0.000317520 |
| No review skill match | 7,499 | 836 | 0.161988 | 0.000314958 |
| Total | 68,870 | 5,852 | 1.478106 | 0.002892540 |

The calls ran sequentially. The ledger span from first start to last finish was
1.752184 seconds, including inter-call overhead. Serialized JSON request bodies
totaled 280,923 bytes. Token counts are provider-reported; cost is estimated from
the frozen rate card, not an invoice. Cached tokens remain unavailable. Baseline
reasoning and downstream model costs remain unknown, so these measurements do
not establish a speedup ratio or complete review-cost comparison. The repeat
responses and both exported original responses passed replay without new calls.

## Separate scripted protocol measurements

The existing protocol benchmark ran five paired samples against pre-#87 runtime
`da0e045d420a890d53a1e0993a0ecdfee5057c72` and the current runtime, with the current
planner, dependencies, and skills. That baseline already includes #89. This is a
265-path synthetic fixture, not either captured pilot scope or live agent work.

| Measurement | Before | After |
| --- | ---: | ---: |
| Materialized worker input bytes | 660,720 | 317,495 |
| Coordinator result bytes | 747,107 | 5,963 |
| Actual default CLI stdout bytes | 0 | 5,963 |
| Repeated validation identity bytes | 196,889 | 0 |
| Shared validation identity bytes | 0 | 17,899 |
| Coordinator operations | 23 | 21 |
| Scripted independent publication attempts | 2 | 1 |
| Scripted formatting retries | 1 | 0 |
| Median total seconds | 0.287246 | 0.322907 |

The legacy CLI was silent, so its coordinator measure includes reading the full
saved result. Four seeded findings survived all runs. The measurements demonstrate
smaller protocol payloads and a removed scripted retry, not faster model reviews
or semantic recall. No fresh downstream paired graph was executed; total review
benefit remains unknown and production adoption stays outside this evaluation.

## Acceptance disposition

| Requirement | Retained evidence or disposition |
| --- | --- |
| Primary inclusion report | Implemented; both original responses replayed at 0.5. |
| Protocol error redaction | `BadStatusLine` and incomplete HTTP reads covered in both credential check and adapter tests. |
| Unknown and failure behavior | Offline cases cover missing evidence, stale bindings, partial answers, model mismatch, timeouts, rate limits, protocol errors, and bounded retries. |
| Coverage preservation | Tests retain the normal plan and required coverage across failure paths; adapter remains separate from the planner. |
| Independent applicability labels | All 315 case/leaf pairs reviewed independently; 312 resolved and three explicitly unknown. |
| Representative source fixtures | Two real and five synthetic scopes retained with source text and dependency context. |
| Request, token, retry, and cost limits | Configurable preflight reservation; each failed or retried attempt retained. Unknown earlier costs prevent a complete cost comparison. |
| Repeat after overhead fixes | Fresh real-scope baselines, all seven live routing requests, and the separate scripted protocol benchmark complete. |
| Full review cost and recall | Unknown; no new downstream paired graph. The conditional adoption proposal #74 was subsequently closed as not planned; #75 tracks future reevaluation. |
| Held-out evaluation | Not triggered in this first phase; the subsequent threshold evaluation freezes a policy before eight new cases. |
| Original evidence retention | Routing records and status receipts retained; full original downstream proofs unavailable. Archival acceptance remains qualified. |
| Adoption | Confirmed after the repeat: retain shadow mode. No automatic additions or pruning. |

## Reproduce offline

Prepare the seven source fixtures without authentication or network access:

```sh
just review-routing-experiment \
  --input agents/.agents/skills/review-graph/scripts/fixtures/routing_evaluation.json
```

Extract the original and repeat replay pairs into a new temporary directory:

```sh
uv run python - <<'PY'
import json
import tempfile
from pathlib import Path

records = json.loads(Path("docs/evidence/typesafe-shadow-2026-10-03.json").read_text())
root = Path(tempfile.mkdtemp(prefix="typesafe-retained-replay-"))
for group in ("original_replays", "live_results"):
    for entry in records[group]:
        case = root / group / entry["case_id"]
        case.mkdir(parents=True)
        for name in ("packet", "result"):
            (case / f"{name}.json").write_text(json.dumps(entry[name], indent=2) + "\n")
        print(f"just review-routing-experiment --replay-case {case}")
PY
```

Run the printed recipe commands. Replay verifies packet/result/request bindings
and records zero new requests. The normal runner writes new output directories;
it does not overwrite these saved responses. Repeat the scripted benchmark with:

```sh
just review-workflow-benchmark da0e045d420a890d53a1e0993a0ecdfee5057c72 5
```

The [experiment guide](../agents/.agents/skills/review-graph/references/routing-experiment.md)
documents explicitly authorized live execution, budget flags, and accounting.

First-phase validation passed `just ci`: 1,178 tests passed and one
native-Windows-only test was skipped. Skill validation, Markdown validation,
secret scanning, and OSV dependency scanning passed. OSV required network access.
An independent implementation review found a retry-cost completeness defect;
the fix and regression passed reviewer verification. Final validation including
the threshold controls passed 1,190 tests with the same platform-specific skip;
the subsequent report records that phase's validation.
