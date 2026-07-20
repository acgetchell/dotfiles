# Rust Benchmark Evidence

Load this reference when implementing an optimization, evaluating a performance claim, or choosing routine, PR, or release evidence.

## Before and After Discipline

1. Pass the relevant correctness checks first.
2. Select the smallest representative benchmark, smoke proxy, allocation counter, or profile for the claimed hot path.
3. Record command, inputs, features, toolchain, environment, and baseline result.
4. Change one bounded performance surface.
5. Rerun the same evidence and relevant correctness regression.
6. Classify improvement, no material change, noise, or regression honestly.

Do not infer speed from code shape when a representative proxy exists. Treat a clear regression as a failed optimization: revert, retune, or narrow it before proceeding.

## Evidence Quality

Prefer realistic sizes, dimensions, distributions, degeneracies, and allocation behavior. Keep parsing, fixture construction, validation, logging, formatting, and unrelated setup outside measured closures.

Small local timing movement may be noise. Judge repeatability, effect size, aggregate impact, and environmental variance. Rerun ambiguous results; do not cherry-pick favorable subcases.

Do not add branches for a benchmark's dimensions, fixture, or seed unless the domain algorithm genuinely differs there and the code remains justified without the timing table.

## Command Roles

Distinguish:

- correctness gate: compile, lint, tests, docs, examples, and harness validity
- focused benchmark: one hot path or allocation concern
- smoke proxy: relatively cheap broad performance signal
- regression guard: branch-versus-baseline PR evidence
- release-signal suite: curated, slower release comparison
- release artifact comparison: existing published measurements
- docs promotion: deliberate release-maintenance update

Read repository benchmark documentation before choosing commands. Do not promote release comparisons or documentation updates into routine pre-commit validation.

## Reporting

Report the representative command, baseline, after result, relevant correctness evidence, noise or limitations, and whether the claim is supported. If no representative evidence exists, say so and recommend the smallest useful benchmark before claiming an improvement.
