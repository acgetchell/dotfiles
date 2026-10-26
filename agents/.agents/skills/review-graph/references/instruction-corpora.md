# Required Instruction Corpora

Repository instruction ownership determines what must be read. Enumerate all
applicable required guidance, including transitive references and mandatory
globs, in planning `instruction_paths`; the runtime additionally discovers
ancestor `AGENTS.md` files. It does not interpret prose to discover every
transitive obligation, select sections, or silently truncate large files.

## Diagnose Before Fanout

Read `instruction_preflight` in the default materialization receipt. It reports
unique file bytes, planned delivery across nodes, repeated bytes beyond one
read per file, maximum bytes per node, and the largest files. The 128 KiB
diagnostic threshold is a prompt to assess context needs, not a model capacity
limit. Full accounting is in `telemetry.instruction_demand`.

Source demand, skill/reference read demand (`protocol_read_demand`), and
serialized execution/worker-input bytes are separate measurements. They are
role-based counts: an instruction file reviewed as source can appear in both
categories. Do not add them as disjoint traffic or interpret file bytes as
provider tokens, actual model reads, latency, cost, or quality measurements.

## Full Text And Continuation

Every execution view's `instruction_context` names a digest-bound manifest with
original paths, SHA-256 identities, byte/line sizes, immutable full-text copies,
and zero-based chunk ranges. Append `--path <original path> --chunk <index>` to
its `read_command` for each chunk. Reads verify the manifest, retained copy,
and current original identity. Each output is at most 16 KiB and preserves UTF-8
boundaries, including files with exceptionally long lines. Read all chunks;
increase the tool output budget or use a smaller direct read if output truncates.
Read the dispatched skill and applicable references as well.

After compaction, lost guidance, or creation of a fresh worker, reload every
required file before continuing. A saved manifest, receipt, digest, previous
worker's declaration, or summary does not establish current model availability
or comprehension. `model_availability` therefore remains `unknown`; publication
still requires truthful declarations of actual reads at their original paths.

Keep a continuation pointer to the execution view and its corpus manifest.
Keep source inspection bounded to the current owned unit while retaining every
applicable instruction. Bounded tool reads prevent output truncation; they do
not make an arbitrarily large mandatory corpus fit a model context. If all
required guidance cannot remain available, report that concrete limitation and
seek a consumer-authorized execution view. Do not cycle through compactions
while claiming that disk receipts satisfy the original instruction.

## Consumer-Authorized Separation

Reduction is an instruction-owner change, not an automatic runtime optimization.
Until the consumer's authoritative entry point permits a different read contract,
retain the complete mandatory corpus. A coordinator's summary alone cannot
authorize an omission.

For an opted-in consumer, prepare a reviewable separation:

1. Inventory original paths, full-text identities, and who owns the instructions.
   Map every applicable rule, applicability condition, command, obligation,
   scientific constraint, and authorship/ownership constraint to its execution
   location. Preserve conflicting or uncertain text for owner resolution.
2. Put current actionable instructions in an execution document. Keep original
   historical rationale accessible and unchanged, with its path and digest;
   history may contain active constraints, so do not classify it by age alone.
3. Have the authoritative entry point explicitly name the execution document and
   permit historical rationale to be consulted only when needed. It must retain
   every applicable obligation and any scope/section-selection conditions.
   Existing session authorization may already cover this ownership change;
   otherwise obtain it before adopting the reduced contract.
4. Capture the changed consumer instructions and replan affected evidence using
   normal instruction-change rules. Set `instruction_paths` to the newly
   authoritative required set. Do not edit a frozen run or reuse stale instruction
   identities. Archive and retain the prior corpus manifest for comparison.

When the entry point still says to read all historical text, follow that rule.
Even byte-identical shared files must be loaded by each fresh worker that owes
the read. The runtime deduplicates storage, not required model delivery.

## Matched Evidence

Run `just test-python
agents/.agents/skills/review-graph/scripts/test_review_graph_instructions.py`.
The fixture compares 44-node graphs with roughly 200 KB of full guidance and an
owner-authorized execution document. It retains historical originals verbatim,
checks all six rule/constraint dimensions, reads every bounded chunk, measures
materialization and scripted delivery/compilation time, and compares 42 seeded
findings. `measurements.json` lives in the test's temporary directory.

These are deterministic transport and publication regressions, not independent
model reviews. Before claiming equivalent review coverage or operational savings
for a real consumer, compare matched source, skills, validation obligations,
worker settings and known defects; measure actual instruction delivery,
compactions, provider usage when available, wall time, findings, missed defects,
and blockers. Preserve uncertainties and adverse results. This fixture leaves
model equivalence and provider usage unmeasured.
