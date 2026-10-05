# TypeSafe Threshold And Coordinator Evaluation

**Current disposition:** production adoption was declined and
[#74](https://github.com/acgetchell/dotfiles/issues/74) is closed as not planned.
The opt-in harness and records are retained for a future pinned revision under
[#75](https://github.com/acgetchell/dotfiles/issues/75). The upstream agent skill
is no longer vendored here. The cases below are historical regression and
development data; a new adoption decision requires fresh held-out evidence.

This is the prospective follow-up to the [first shadow routing evaluation](typesafe-shadow-evaluation.md)
for [issue #73](https://github.com/acgetchell/dotfiles/issues/73). The first seven
cases became development data. On 2026-10-03, before selecting new cases or
collecting their labels, the candidate policy was frozen at **0.70 for advisory
inclusion, with coordinator assessment for 0.50 ≤ p < 0.70**. Eight new service
requests ran on 2026-10-04. The model and question template remained
`jev-1.13.0` and `applicability-noul-v1`.

**Retain shadow mode.** The candidate reduced unnecessary selections but missed
one additional applicable concern, so it failed the frozen success rule. The
new controls remain opt-in and the default comparison cutoff stays at 0.50.

The [supporting records](evidence/typesafe-threshold-2026-10-04.json) retain the
frozen policy, source selection and licenses, both independent label sets,
ordinary routing baseline, blinded assessment inputs, service attempts, usage,
coordinator judgments, and replayable packet/result/assessment triples.

## Design and boundaries

A fresh worker selected six bounded public source scopes from immutable commits,
plus a no-match text edit and a Python/documentation control. Source selection
preceded labels and Jev results. The source excerpts total 36,002 bytes; owned
units are explicit, and dependency excerpts provide context rather than expand
ownership. This convenience sample covers several languages and overlapping
skills, but it is not a representative benchmark or a model-pretraining holdout.

| Repository | Frozen commit | Owned scopes |
| --- | --- | --- |
| research-repo-tools | `0a02204d4a889dfc97f55286c008397ced05d6ad` | Notebook loading; release-pair ordering |
| delaunay | `1892b823c4600b56f9720517ed34dad4b155fb0f` | Allocation result wrapper; CLI artifact output |
| CDT-plusplus | `b8e35a6c1accb0837a6d8cfa13eb3beb739c906a` | MPFR value operations; move outcome model |

Two fresh model workers independently labeled all 360 case/leaf pairs without
seeing prior outcomes, one another's labels, the baseline, or new scores. Only
matching Boolean labels enter quality counts; conflicts and unknowns remain
null. These are independent model judgments, not human consensus or evidence
that a code defect exists. Shared model biases and subjective ownership remain
limitations.

A separate ordinary coordinator used the current catalog, deterministic path
projections, source excerpts, and semantic ownership guidance to freeze all 360
baseline decisions before inference. Jev received the same source evidence and
all 45 catalog questions, without labels or baseline answers. The instruction
context differs: the ordinary coordinator can consult full skill guidance, while
Jev receives catalog semantic triggers.

After all eight responses, another fresh coordinator received source, relevant
skill context, and only the 22 borderline candidate identities. It did not see
probabilities, expected labels, baseline decisions, or other Jev judgments. Its
decisions were frozen before scoring. The saved assessment binds the exact
packet, result, inclusion threshold, and coordinator floor; changing any of
those inputs invalidates replay. No cases were excluded after results, and no
further threshold tuning was performed on this evaluation.

The frozen success rule requires fewer labeled unnecessary selections than the
0.50 policy with no additional missed applicable concerns. Unresolved labels and
decisions are reported separately; additional unresolved applicable decisions
would also prevent a clean success claim.

## Results

There are 354 resolved labels and 6 unresolved labels. The table scores
only resolved labels. Accuracy includes every resolved label in its denominator;
unresolved predictions are not counted as correct. Precision excludes unresolved
predictions, and recall is the lower bound against all labeled positives.

| Method | Applicable selected | Applicable missed | Unnecessary selected | Unknown applicable | Precision | Recall | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Jev ≥ 0.50 | 37 | 9 | 21 | 0 | 63.8% | 80.4% | 91.5% |
| Jev ≥ 0.70 | 30 | 16 | 7 | 0 | 81.1% | 65.2% | 93.5% |
| Jev ≥ 0.70 + coordinator band | 36 | 10 | 10 | 0 | 78.3% | 78.3% | 94.4% |
| Ordinary coordinator | 45 | 1 | 3 | 0 | 93.8% | 97.8% | 98.9% |

The combined policy **does not meet the frozen success rule** on this sample.
It changes labeled unnecessary selections from 21 to 10 and missed applicable
concerns from 9 to 10, with 0 unresolved applicable decisions.

Always selecting no specialist would score 87.0% accuracy while missing
every applicable concern. Accuracy alone is therefore insufficient evidence of
useful routing. The combined method selects 48 of all 360 candidate pairs;
2 of those selections have unresolved expected labels.

| Case | Combined applicable selected | Combined applicable missed | Combined unnecessary selected | Unresolved labels |
| --- | ---: | ---: | ---: | ---: |
| rrt-notebook-load-boundary | 3 | 1 | 1 | 0 |
| rrt-release-pair-ordering | 2 | 0 | 0 | 0 |
| delaunay-allocation-result-wrapper | 8 | 0 | 4 | 3 |
| delaunay-cli-artifact-output | 7 | 3 | 3 | 0 |
| cdt-mpfr-value-operations | 9 | 2 | 0 | 1 |
| cdt-move-outcome-model | 4 | 3 | 2 | 2 |
| synthetic-lantern-color-edit | 0 | 0 | 0 | 0 |
| synthetic-word-tally-and-guide | 3 | 1 | 0 | 0 |

Every per-candidate reason and overlapping risk-category count is retained in
`live_results` and `quality_by_risk`. These classify review applicability, not
code defects, severity, calibrated probabilities, or demonstrated review recall.

## Measurements and limitations

The eight sequential calls returned all 360 typed judgments with no API failures
or retries. They reported 85,668 input tokens and 6,688 output tokens, for
an estimated **$0.003598056** at the frozen published rate of $0.042 per
million input tokens and free output. The worst-case preflight reservation was
$0.021504, eight requests, zero retries, and 512,000 input tokens.

Summed adapter time was 1.447896 seconds; the span from first request start to
last finish was 1.739189 seconds, including inter-call overhead. Request
bodies totaled 331,601 serialized bytes. Provider-reported tokens and estimated
cost are distinct from source byte counts and invoice amounts; cached tokens
remain unknown. Two 1Password authorization attempts timed out before the runner
started, with no API requests. The long authentication/UI wait is excluded from
these adapter and decision timings.

The ordinary baseline measured 571.607 seconds and 22 CLI invocations, including
eight nested projection commands. It read the 95,352-byte source packet five
times and the 16,813-byte catalog twice, with guidance and projection reads
itemized separately. The borderline coordinator measured 322.965 seconds,
five CLI operations, and 30 explicit reads totaling 519,554 bytes, including
three reads of its source/candidate packet. Packet rereads are not unique source
bytes or provider tokens. Both timings include reasoning, guidance, and local
bookkeeping within their recorded boundaries. The baseline, sequential API
phase, and borderline assessment did not overlap.

The borderline task involved 22 judgments instead of 360, but this does not
establish an equivalent-work speedup: it had different instruction context,
reused preassembled evidence, and left concerns below 0.50 unassessed. Provider
usage for both coordinators and all downstream review costs remain unavailable.
The higher threshold does not save input tokens for the same batched request.
There was no downstream dispatch, paired review, or production routing change.

## Disposition

**Retain shadow mode and keep these controls opt-in.** The combined policy
improved accuracy and precision on this sample, but recall fell from 80.4% to
78.3%. The ordinary coordinator performed better on these labels: 45 applicable
selections, one miss, and three unnecessary selections. The new settings are
useful experiment controls; these observations do not justify changing the
normal selector or the default 0.50 comparison cutoff.

The additional combined-policy miss is `python.support-scripts` in the notebook
loading scope, at Jev probability 0.52. The blinded coordinator judged the owned
parser/model boundary outside support-script ownership; both labelers had marked
it applicable. That disagreement remains a miss relative to the frozen labels;
it was not relabeled after observing the result. The remaining nine misses were
already below 0.50. Every miss and the coordinator's reasons are retained.
The genuine no-match text case remained unselected by all four methods.

On the original development cases, moving from 0.50 to 0.70 reduced labeled
unnecessary selections from 17 to six but missed one of 21 applicable concerns.
That tradeoff motivated evaluating the coordinator band. The new result shows
why those already-seen cases could not establish general accuracy or justify a
default change. Any further tuning needs another held-out evaluation. The
conditional adoption proposal #74 was subsequently closed as not planned;
#75 tracks future reevaluation. Complete-review benefit remains unmeasured.

## Reproduce offline and validation

Extract the retained packet/result/assessment triples without authentication:

```sh
uv run python - <<'PY'
import json
import tempfile
from pathlib import Path

records = json.loads(Path("docs/evidence/typesafe-threshold-2026-10-04.json").read_text())
root = Path(tempfile.mkdtemp(prefix="typesafe-threshold-replay-"))
for entry in records["live_results"]:
    case = root / entry["case_id"]
    case.mkdir()
    for name in ("packet", "result", "assessment"):
        (case / f"{name}.json").write_text(json.dumps(entry[name], indent=2) + "\n")
    print(f"just review-routing-experiment --replay-case {case} --inclusion-threshold 0.5")
    print(
        f"just review-routing-experiment --replay-case {case} "
        f"--inclusion-threshold 0.7 --coordinator-floor 0.5 "
        f"--coordinator-assessment {case / 'assessment.json'}"
    )
PY
```

Run the printed commands. All eight public pairs replayed at both policies;
all eight assessment bindings verified with zero new requests. Packets, requests,
results, and assessment decisions are unchanged in the public export. Only
machine-local provenance/instrumentation paths in the source-selection and
baseline artifacts were replaced with placeholders. Original and public artifact
digests are listed separately, so the frozen manifest retains its original meaning.

`just ci` passed with **1,190 tests and one native-Windows-only skip**. The focused
adapter and credential-check suite passed 87 tests. An independent implementation
review found a stale-assessment binding gap; the fix now recomputes packet,
request, and result digests and requires an explicit matching model. The reviewer
verified rejection of altered probabilities, changed source, and missing bindings.
This is implementation validation, not a full review-graph proof. Final Markdown,
skill, and secret checks cover the reports and evidence; the locked dependencies
also passed OSV scanning. Historical proof-retention limits remain documented in
the first-phase report.
