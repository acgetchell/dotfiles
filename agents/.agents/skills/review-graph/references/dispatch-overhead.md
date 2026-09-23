# Dispatch Overhead Measurement

## Repeatable Protocol Benchmark

Run from the dotfiles checkout:

```sh
just review-workflow-benchmark
# Compare only the current uncommitted runtime against the checked-in runtime:
just review-workflow-benchmark HEAD
```

The command prints an external `report.json` path. It reads the selected trusted
Git revision with `git show`; it does not change Git state or execute repository
validation recipes. The baseline revision must be available locally. For a
chosen new output directory or repeat count, use
`scripts/review_graph_benchmark.py --help` inside this skill.

Each run creates 18 Python/tooling/documentation files, performs exhaustive
catalog routing, and retains nine audits, one conclusion-blind independent
dispatch, three validators, and two syntheses. Both versions use the current
planner, schemas, and skills. A four-slot wave projection preserves dependencies
and serializes validators. It is a cost model, not actual concurrent model work.

Five paired trials alternate baseline/current execution order. Each materializes
all workers, follows source packets with direct-read fallback, publishes and
compiles nine scripted audit payloads, and checks exact payload bytes, approval
receipts, accepted status, and equality of four seeded findings. Trials retain
dispatch manifests, receipts, source/implementation identities, and individual
timings. Independent workers receive raw source only. Independent review,
validators, and syntheses are not executed in this protocol benchmark; no
semantic recall or model latency is inferred from seeded transcripts.

The September 2026 rerun against `eeead7c646a45ca8227bc7fc057e6f2e1bdf52bf`
measured:

| Measurement | Before | After |
| --- | ---: | ---: |
| Worker wrapper bytes | 344,422 | 233,116 |
| Prompt text bytes (subset of wrappers) | 117,887 | 23,293 |
| Scripted direct source reads | 92 | 18 |
| Scripted repeated direct source reads | 74 | 0 |
| Scripted packet bytes read | 0 | 20,976 |
| Coordinator API operations (materialize + nine publications/compilations) | 28 | 19 |
| Projected publication CLI invocations for all 15 workers | 30 | 15 |
| Median materialization time | 51.54 ms | 45.87 ms |
| Median measured protocol time | 105.61 ms | 96.93 ms |
| Seeded findings preserved | 4 | 4 |

The first optimized implementation was already merged in PR #76. A separate
comparison against `7e01574` measured approximately 8% fewer wrapper bytes from
moving repeated observation lists into digest-bound references. Publication CLI
invocations were already 15 at that revision. The new Python transaction helper
reduces caller API operations while retaining the same review/persistence gates.

Byte counts depend on output-path lengths. Direct source reads exclude the
materializer's packet construction and count the scripted consumer behavior,
not observed model/tool reads. Packet reads and repeated semantic context remain
real costs. Elapsed differences are small and vary between runs; these results
demonstrate reduced protocol/context overhead, not a reliable wall-clock speedup.
Actual model review time remains explicitly null. Live comparisons must record
worker reads, elapsed review work, adjudicated findings, and orchestration time
separately against the same captured state and concurrency limit.

## Earlier Structural Measurement

The September 2026 structural replay compared the runtime at commit
`eeead7c646a45ca8227bc7fc057e6f2e1bdf52bf` with the publication, shared-packet,
and prompt changes for issue #72. Both used the same current planner, schemas,
and skill files to isolate dispatch protocol costs.

The synthetic fixture had 18 Python/tooling/documentation files and 15 nodes:
nine focused audits, one independent review, three validators, and two syntheses.
The plan configured four slots. Five materializations ran per version. No model
workers or validation commands ran; this does not measure end-to-end review
latency, actual worker source reads, or semantic recall.

| Measurement | Before | After |
| --- | ---: | ---: |
| Worker wrapper bytes | 336,944 | 253,768 |
| Prompt text bytes | 107,980 | 22,928 |
| Separate shared source packet bytes | 0 | 3,800 |
| Required publication process invocations for 15 workers | 30 | 15 |
| Median materialization time | 33.25 ms | 34.64 ms |

The packet represented 18 distinct files that otherwise appeared in 66 audit
file requests. Those counts describe potential read demand; worker reads were
not observed. Prompt bytes are a subset of wrapper bytes. Packet bytes are
additional storage. Publication counts come from the protocol, not a timed
publication run. Small timing differences are not evidence of a speedup.

For a live follow-up, retain the captured plan/source identity and dispatch
telemetry, record worker source reads and coordinator invocations, and measure
elapsed time and adjudicated findings under the same four-slot budget. Compare
blocked and recovered attempts separately from successful validation. Keep the
independent reviewer blind to specialist conclusions and shared packets.
