# Dispatch Overhead Measurement

## Partial Recheck Proof Transport (#128)

The fixed regression fixture owns `pyproject.toml` and
`tests/tooling/test_adoption.py` in a repository with exactly 100 captured paths.
Only the test changes; configuration coverage is reused. Two seeded findings,
unit dependencies, validation requirements, and a routing handoff survive
publication, compilation, and evidence verification.

Reproduce the byte measurement from the checkout:

```sh
UV_CACHE_DIR=.uv-cache uv run --locked pytest -q -s \
  agents/.agents/skills/review-graph/scripts/test_review_graph_coverage_proofs.py \
  -k fixed_partial_recheck_dispatch_bytes
```

The 2026-10-07 local run measured these serialized bytes. Absolute temporary and
skill paths affect exact sizes. The inline comparison replaces only the new
dispatch's execution view with the complete proof and serializes the same
worker wrapper; it is a controlled representation comparison, not a historical
runtime replay.

| Artifact or representation | Bytes |
| --- | ---: |
| Fresh worker input | 16,771 |
| Partial recheck with inline proof (comparison) | 55,975 |
| Partial recheck with external proof | 19,889 |
| Compact execution view alone | 1,747 |
| Full external proof alone | 25,591 |
| Partial publication contract | 3,195 |

Externalizing the proof reduces the partial worker input by about 64% against
the inline comparison. Both complete 100-entry fingerprint arrays remain in the
read-only proof artifact and the compiler-bound plan. Neither worker input nor
publication contract embeds them. Tests also reject missing, byte-altered, or
symlinked proofs, forged projections and partitions, altered dependency or
instruction claims, unsupported snapshots, and omitted inherited obligations.
Existing staging regressions exercise inherited semantic Git dependencies.

These are scripted protocol and byte measurements. Model tokens, model cost,
review latency, and semantic finding recall are unobserved; the printed report
uses `null` for model measurements. Retaining two seeded findings demonstrates
provenance preservation, not model recall.

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

Each run defaults to 265 Python/tooling/documentation files (`--scale 20`), performs exhaustive
catalog routing, and retains nine audits, one conclusion-blind independent
dispatch, three validators, and two syntheses. Both versions use the current
planner, dependencies, and skills; each runtime loads its own versioned operation
input schema from Git. Historical formats are used only in temporary benchmark
storage and are not accepted by the current runtime. A four-slot wave projection preserves dependencies
and serializes validators. It is a cost model, not actual concurrent model work.

Five paired trials alternate baseline/current execution order. Each materializes
all workers, follows source packets with direct-read fallback, publishes and
compiles nine scripted audit payloads, and checks exact payload bytes, approval
receipts, accepted status, and equality of four seeded findings. Each also replays
one independent transcript through publication/compilation. The legacy transcript
starts with a deliberate `Check`/`Inspected` label mismatch, then retries with
correct labels; structured input supplies stable IDs and the same observations.
These attempt/retry counts describe this scripted failure, not observed model retry
rates. The report retains source/implementation identities, individual timings,
byte counts, and verification outcomes. Fixtures and protocol artifacts are
scratch data and may be deleted after inspecting the comparison. Independent
workers receive raw source only. No actual model review,
validator commands, or synthesis runs in this protocol benchmark; no semantic
recall or model latency is inferred from seeded transcripts.

## Fail-Fast Validation And Worker Provenance (#116, #117)

The 2026-10-05 local measurement used macOS arm64, Python 3.14.7, uv 0.12.23,
a pre-existing locked environment, and a warm cache with `UV_OFFLINE=1`.
No installation or setup time is included. The checked-in baseline was
`2b585b3b3a5d45dcd4cfa7a5ae8923a018fac968`.

For skill checks, three alternating before/after trials ran the baseline
`check-skills` recipe extracted with `git show` and the new recipe against the
same final validator and 66 skill entrypoints. The baseline recipe was stored
outside the checkout and invoked with `just --justfile <baseline.just>
--working-directory "$PWD" check-skills`; nested single-skill checks used the
unchanged `skill-check` recipe. Separate PATH-wrapper traces counted launches;
elapsed samples had no tracing. These counts cover the named launchers, not
every OS process. Both source and Git-state digests matched before and after.
The source manifest digest, before adding this measurement note, was
`8defae54928448656ee390fbd593b5dd5e5dc322c2e228d8c2bc99a2fa802c36`.

| Skill-check boundary | Before | After |
| --- | ---: | ---: |
| `just` launches, including outer recipe | 67 | 1 |
| `uv run` launches | 66 | 1 |
| `uv --version` probes | 67 | 1 |
| Validator Python launches | 66 | 1 |
| Median wall time, seconds | 8.463 | 0.196 |

`just ci` now orders the 17 prompt/routing guards before static checks, batched
skill checks, and the remaining Python tests. Just's dependency deduplication
runs the guard recipe once; complementary pytest markers keep the two execution
sets disjoint and exhaustive. `just test-python` uses the same two phases.
Collection tests verify their union, and a temporary launcher injects an actual
budget assertion failure to prove the original diagnostic stops phase two.
Fixtures live outside the reviewed checkout; batch tests also verify unchanged
Git status/index entries and ignored, deleted, untracked, and nested scope.

Keep these elapsed boundaries separate:

- The standalone contract gate's three-trial median was 0.698 seconds, including
  Just, uv, pytest startup, collection, and execution.
- A separate static-only run took 25.429 seconds: shell/Git configuration,
  Just/TOML/YAML/Markdown, GitHub Actions, Semgrep and fixtures, and Python
  format/lint/type checks. It excluded skill validation and pytest execution.
- The full CI run took 512.90 seconds externally. Pytest reported 0.42 seconds
  for 17 guards and 470.29 seconds for the remaining phase: 1,238 passed and two
  native-platform skips. The final focused rerun passed 99 tests in 10.97 seconds.
  These separately measured boundaries must not be summed or used to infer a
  full-suite before/after speedup.

For dispatch transport, `just review-workflow-benchmark HEAD 3` compared the
baseline and final runtime on the same 265-file fixture and 15-node plan. Its
source identity was
`sha256:dbb4bb61f2f4505faafdcaf82618c32c0aef2fa358aeceb105ac7ed0d6e620de`;
the final runtime digest was
`sha256:72e4868511755dc3713eaad0c4f043645d86c097038302eb471d4da3b9bbae96`.
Current planner, dependencies, and skill templates were held constant.

| Dispatch replay boundary | Before | After |
| --- | ---: | ---: |
| Total worker-input bytes | 318,640 | 335,871 |
| Worker-prompt bytes, included above | 32,293 | 38,474 |
| Independent scripted publication attempts | 1 | 1 |
| Independent formatting retries | 0 | 0 |
| Median materialization seconds | 0.215 | 0.194 |
| Median protocol seconds | 0.359 | 0.329 |
| Seeded findings preserved | 4 | 4 |

The extra bytes carry owned/context read fragments, exact command declarations,
conservative branch-diff guidance, and the distinction between payload writes
and authorized capture/proof writes. Existing prompt budgets remain unchanged.
Native publication/compiler regression tests replay the emitted audit and
independent fragments successfully on their first attempt and reject unsupported
or compound discovery declarations, false scope expansion, and context-only
adversarial checks. These are scripted outcomes, not measured model retry rates.

A separate fresh live worker inspected `tool.py`, nearby `state.rs`, and
`git diff origin/main -- tool.py` in a temporary Git fixture. It published on
attempt one with zero environment approval requests or tool failures. Native
`compile-node` verified equal before/after captures and exact sealed bytes and
journaled acceptance. An earlier setup used macOS path aliases inconsistently;
compilation rejected that capture. Rebuilding with resolved paths fixed the
fixture without weakening the fingerprint check.

Model token counts, inference cost, and attributable retry latency were
unavailable. No token savings, semantic recall improvement, or reliable protocol
speedup is inferred from source bytes or these small timing differences.

## Compact Receipt And Evidence Replay (#87)

Three paired trials against `da0e045d420a890d53a1e0993a0ecdfee5057c72` (the merged
#89 implementation) used the default 265-file mixed whole-repository fixture.
The CLI is invoked directly; measurements include stdout and actual saved worker
inputs, with per-node bytes retained in every sample.

| Measurement | Before | After |
| --- | ---: | ---: |
| Actual materialization stdout bytes | 0 (silent) | 5,215 |
| Coordinator result bytes¹ | 714,020 | 5,215 |
| Full saved materialization bytes | 714,020 | 326,854 |
| Total worker-input bytes | 630,809 | 284,083 |
| Repeated full validation-identity bytes | 195,921 | 0 |
| Separate shared identity bytes | 0 | 17,811 |
| Coordinator API operations, including independent replay | 23 | 21 |
| Independent scripted publication attempts | 2 | 1 |
| Independent formatting-only retries | 1 | 0 |
| Seeded findings preserved | 4 | 4 |

¹ The old CLI prints nothing, requiring a saved-result read for coordinator
handoffs. The new default receipt provides them directly. This is a comparison
of that workflow's context demand, not a claim that stdout shrank from zero.

Worker inputs shrank about 55%; the receipt uses about 99.3% fewer bytes than
the prior complete-result read. Full proof artifacts and shared sidecars remain
on disk. Median materialization/protocol times were 118.16/260.41 ms before and
166.72/288.71 ms after; this replay demonstrates context savings, not a measured
execution speedup or API token-cost reduction. Path lengths affect byte counts;
no tokenizer or model billing is inferred. Native and structured transcripts
retain the same substantive observations; only the structured protocol owns labels.

## Earlier Publication And Shared-Packet Replay

The following smaller 18-file measurements predate #87 and used the older default
baseline; use `--baseline-ref eeead7c646a45ca8227bc7fc057e6f2e1bdf52bf --scale 1`
for that historical comparison.

The September 2026 rerun against `eeead7c646a45ca8227bc7fc057e6f2e1bdf52bf`
measured:

| Measurement | Before | After |
| --- | ---: | ---: |
| Worker wrapper bytes | 344,422 | 233,116 |
| Prompt text bytes (subset of wrappers) | 117,887 | 23,293 |
| Scripted direct source reads | 92 | 18 |
| Scripted repeated direct source reads | 74 | 0 |
| Scripted packet bytes read | 0 | 20,976 |
| Audit-only coordinator API operations (materialize + nine publications/compilations) | 28 | 19 |
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

## Publication Contract Preflight

The #126/#130/#131 follow-up was replayed against
`9304d0b` with the same 265-path, 15-worker fixture and one paired sample.
The new dispatches expose only the optional coverage shape, exact artifact-root
rules, and synthesis binding examples; the synthesis plan is a shared hashed
runtime sidecar. Independent dispatches receive no additional context.

| Scripted measurement | Before | After |
| --- | ---: | ---: |
| Total worker input bytes | 335,871 | 352,748 |
| Audit input bytes (nine workers) | 188,108 | 192,869 |
| Validator input bytes (three workers) | 73,244 | 74,084 |
| Synthesis input bytes (two workers) | 29,687 | 40,963 |
| Independent input bytes | 44,832 | 44,832 |
| Worker prompt bytes | 38,474 | 42,718 |
| Audits using optional coverage partitions | 0 | 9 |
| Audit publication attempts | 9 | 9 |
| Formatting-only retries | 0 | 0 |
| Coordinator API operations | 21 | 21 |

Each partitioned audit published and compiled on its first attempt, preserving
all four seeded findings. Input bytes increased 5.0%; the optional shape itself
is under 400 compact JSON bytes per audit. These are deterministic protocol
measurements, not observed model retry rates or speedups. Regression fixtures
also verify reference-only corrections, shared validators, distinct hosted
evidence, required unexecuted platforms, and unchanged evidence across repair
epochs; no platform checks are executed by this benchmark.
