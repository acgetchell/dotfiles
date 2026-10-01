# TypeSafe Routing Experiment

Use this workflow when a TypeSafe applicability comparison is requested. Jev
runs in shadow mode: ordinary routing, mandatory nodes, validation, and proof
acceptance continue to control execution. No experimental response is a routing
override or proof of semantic correctness.

## Run The Pilot

From the dotfiles checkout, inspect the synthetic development inputs offline:

```sh
just review-routing-experiment
```

Make the three development requests with an injected credential:

```sh
just typesafe-local 'op://<vault>/<item>/<field>' \
  just review-routing-experiment --live
```

In a cloud environment that already supplies `TYPESAFE_API_KEY`, use
`just review-routing-experiment --live` directly. The client honors the HTTPS
proxy. It neither follows redirects nor persists credentials or raw responses.
Each invocation gets a new external artifact directory. There are no automatic
retries; a failed attempt is recorded and ordinary graph routing continues.

The portable skill entrypoint is
`uv run python "$SKILLS_ROOT/review-graph/scripts/review_graph_routing_experiment.py"`.
Only the Python standard library and sibling graph modules are required.

The default model is pinned to `jev-1.13.0`. The dated rate card estimates input
cost from provider-reported usage; output is currently free. A different returned
model fails the comparison and leaves cost unavailable. Check [TypeSafe models](https://docs.typesafe.ai/models)
before updating the model and rate card together.

## Compare A Real Scope

Use `--input <case.json>` with the shape in
[`routing_pilot.json`](../scripts/fixtures/routing_pilot.json). Supply the actual
review request, source text, relevant dependency context, and explicit completeness
flags. Record the current selector's decisions before examining Jev's answers.
The same frozen scope should be available to both methods; document extra context
seen by either method. Never silently truncate or omit dependencies to fit a limit.
The pilot rejects scopes above 32 KiB and requests above 96 KiB; these conservative
byte limits are not token estimates.

Use `--plan <plan.json>` to import the existing graph's routing decisions instead
of manually entering a baseline. The input may be a plan or bootstrap bundle.
The plan digest is retained, but importing a plan does not independently verify
that its source capture matches the supplied text. Establish that correspondence
before treating the comparison as controlled evidence. Unconsulted, blocked, and
excluded baseline entries remain unknown, not negative labels.

Every catalog leaf receives its own Noul question in one request, including leaves
outside path-matched language surfaces. Source context is shared; questions contain
the skill name and catalog semantic triggers. Syntheses, routers, and independent
review remain graph-owned. The packet retains catalog and skill digests, prompt
version, exact request, baseline, labels, and response model. Baseline judgments
and expected answers are never sent to Jev.

Probabilities at or below 0.2 are provisional negatives, at or above 0.8 provisional
positives, and others uncertain. These thresholds are uncalibrated. Incomplete
context makes every decision uncertain, regardless of its probability. Failures
also remain uncertain. The comparison reports disagreements and a stable 20%
agreement sample for adjudication. Omitted labels are unknown. The pilot's sparse
labels and frozen coordinator baseline are provisional and share an author; they
cannot establish independent recall or cost savings.

Quality counts separately compare Jev, the supplied baseline, and deterministic
path projection alone against available labels. Unresolved required labels reduce
the reported recall lower bound. These are partial-label pilot metrics; the path
projection is only one component of the ordinary selector, not its full judgment.

The report also sweeps inclusion cutoffs of 0.1, 0.2, 0.35, 0.5, 0.65, and 0.8.
Each cutoff includes every skill at or above that probability. Compare selection
counts and labeled errors; a missing specialist generally costs more than an extra
review, but extra reviews still contribute to the total budget. These alternatives
do not alter the shadow execution policy. Reassess stored probabilities for free:

```sh
just review-routing-experiment --replay-case <experiment-case-directory>
```

Replay verifies the saved input digest, writes a new comparison, and records no
new API usage. It does not modify prior reports or relabel the held-out split.

`--split held-out --live` runs only the reserved split. Freeze prompts and
thresholds before using it; inspecting or tuning against its outcomes consumes
that holdout. Expand with independently labeled real cases before promoting Jev
to routing control. This runner deliberately provides no promotion switch.

## Account For The Whole Graph

Set `REVIEW_GRAPH_USAGE_LEDGER` to `<proof-store>/usage.jsonl` for graph runtime
commands. Each operation records a start and completion with measured wall time;
failure and interruption do not erase earlier work. Its zero model cost applies
only to the deterministic process and excludes coordinator inference and compute.

For coordinator/model stages, use `review_graph_usage.py start` before work and
`finish` afterward. Use stages such as `routing-baseline`, `specialist:<node-id>`,
`validation:<node-id>`, `synthesis:<node-id>`, and `proof-coordination`. Keep the
returned attempt ID. Supply actual provider/tool usage when exposed; otherwise
use null counts and `measurement_source: "provider usage unavailable"`.
Do not derive request tokens from account-wide allowance changes or byte counts.
Each retry or fallback needs its own attempt; imported baseline measurements are
reference data and must not be counted as new requests when replaying comparisons.

The `--usage` JSON for `finish` accepts `input_tokens`, `output_tokens`,
`cached_input_tokens`, `elapsed_seconds`, `cost_usd`, `cost_basis`
(`measured`, `estimated`, or `unavailable`), and required `measurement_source`.
Missing numeric fields remain null. Estimated cost must identify its rate source;
subscription allowance is not an API invoice. Batched per-question costs are not
measured and are not allocated by this runner.

```sh
just review-usage report <proof-store>/usage.jsonl <experiment-case>/usage.jsonl
```

Include the compact stage/provider totals, unknown measurements, and unfinished
attempt count in the graph's final report, even for blocked or abandoned work.
Compare total cost only when baseline, retries, fallback, and downstream review
coverage are accounted for. A cheap routing call alone does not establish savings.
