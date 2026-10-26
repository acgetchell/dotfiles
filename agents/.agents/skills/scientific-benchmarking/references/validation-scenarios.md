# Validation scenarios

Use these when maintaining this skill. Metadata checks establish structure, not
sound benchmark decisions. Give an independent evaluator the skill and the
[fictional input cases](fixtures/benchmark-cases.md), without this rubric or prior
conclusions. Request a bounded audit and proposed changes, not execution. Inspect
its decisions and actual tool actions; do not test for particular wording.

| Case | Observable acceptance condition |
| --- | --- |
| A: command ownership | Identifies overlapping allocation jobs and report-triggered collection; makes internal stress profiling opt-in while retaining Criterion repetitions, untimed preflight, correctness tests and distinct baseline/current evidence |
| B: report retry | Valid complete evidence can render again with zero collection calls; preserves original provenance and distinguishes render time; missing scratch cannot silently select history |
| C: changed methodology | Rejects ratios from incompatible baselines; proposes affected remeasurement only when authorized, without backfilling metadata, deleting history, or preserving a defective plan |
| D: coverage | Flags missing required, unexpected, duplicate and truncated cases even when selected report rows look complete; distinguishes declared extra diagnostics from unexpected observations |
| E: metrics | Separates deterministic allocation counts, instrumented timing, uninstrumented timing and noisy RSS; checks counter isolation and declines unsupported speed/memory claims |
| F: fixture boundary | Preserves independent correctness tests and untimed result checks; times public validation when that is the operation; resets mutations without removing construction from construction workloads |
| G: valid reuse | Accepts a presentation-only rerender of complete compatible evidence, preserving baseline-phase peers; does not demand a new campaign or invent an upstream feature |
| H: routing and authorization | Keeps a prose-only change narrow and respects all execution prohibitions, including hidden Git/worktree effects of measurement wrappers |

Retain a brief assessment of the inputs, outputs, actual actions, failures and
limitations. Distinguish an offline behavioral exercise from native execution or
measured evidence. Correct only demonstrated decision problems, then repeat
affected cases. Do not create a second benchmark engine or wording-matching test
suite to validate these instructions.

For structural checks use `just skill-check
agents/.agents/skills/scientific-benchmarking`, `just check-skills`,
`just markdown-check`, and `just yaml-check`. Check relevant existing instruction
contracts when editing coordinating skills. These checks do not collect scientific
benchmark measurements.
