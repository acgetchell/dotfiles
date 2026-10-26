# Scientific benchmarking skill evaluation

On 2026-10-26, the new
[scientific-benchmarking skill](../agents/.agents/skills/scientific-benchmarking/SKILL.md)
was evaluated through an independent, offline scenario pass. The evaluator
received the skill, its evidence contract, and the
[fictional cases](../agents/.agents/skills/scientific-benchmarking/references/fixtures/benchmark-cases.md).
It did not receive the assessment rubric, repository examples, or prior
conclusions. This was behavioral validation of instructions, not benchmark
execution or a performance measurement.

| Case | Observed decision |
| --- | --- |
| A | Removed overlapping memory collection jobs and stopped report rendering from collecting new samples; retained statistical repetitions, preflight, correctness tests and distinct baseline/current/release phases |
| B | Selected the complete scratch run for rendering, preserved measurement provenance, and rejected missing-envelope fallback to older history |
| C | Rejected ratios across different timed operations and environments; preserved history and proposed authorized common-harness remeasurement |
| D | Rejected missing, duplicate, unexpected and truncated observations despite complete displayed rows; recognized the declared diagnostic as allowed |
| E | Withheld speed/memory claims from contaminated allocation counters, incompatible instrumented timings and a single RSS delta |
| F | Moved unrelated query setup/checks/logging outside timing, retained public validation and fresh construction, isolated mutations, and preserved the failing fixture and correctness tests |
| G | Accepted an eligible presentation-only rerender without resampling; preserved peer phase origins and uncertainty limits |
| H | Limited a prose-only task to the typo and appropriate Markdown validation; rejected the measurement wrapper's hidden prohibited effects |

The initial Case A input did not specify whether profiling served a public
contract. The fixture was clarified to identify private stress diagnostics and
a separate public allocation correctness test. A focused reassessment moved all
profiling to an opt-in job while retaining the public test in routine PR checks.
No skill instruction changes were required by the observed decisions. All eight
cases met the final [behavioral criteria](../agents/.agents/skills/scientific-benchmarking/references/validation-scenarios.md).

The evaluator used three read-only file reads initially and one read of revised
Case A. It made no edits, external requests, Git mutations, release operations,
uploads, or benchmark runs. Its suggested validation actions were not counted as
executed checks. These bounded synthetic cases do not establish native workflow
behavior, runtime improvements, or exhaustive routing accuracy.

Implementation validation passed the focused skill check, repository-wide skill
metadata checks, Markdown/YAML checks, and all 24 existing instruction-contract
tests. Reference source paths were checked locally. Stow preview showed only the
new skill link; application and full managed-link verification succeeded.
The [repository examples](../agents/.agents/skills/scientific-benchmarking/references/repository-examples.md)
separately record the inspected source revisions and limits of that inspection.
