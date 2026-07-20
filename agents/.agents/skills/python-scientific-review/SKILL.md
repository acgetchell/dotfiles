---
name: python-scientific-review
description: "Review Python numerical, geometric, statistical, stochastic, and scientific-computing behavior for mathematical validity, numerical robustness, reproducibility, independent scientific oracles, data conventions, and interoperability. Use for NumPy, SciPy, scientific dataframe computation, generated scientific fixtures, and Python validation of native libraries. Route generic parsing, packaging, support tooling, notebook structure, and test mechanics to focused skills."
---

# Python Scientific Review

Review scientific Python as correctness-critical software. Establish the intended mathematics and data conventions before commenting on implementation style or speed.

## Scope And Boundaries

Use changed-code mode by default and whole-repository mode only when requested.

- Own formulas, algorithms, numerical stability, degeneracy, stochastic validity, scientific reproducibility, independent oracles, units, coordinates, and scientific data conventions here.
- Route raw data/model parsing to `python-parse-dont-validate`.
- Route notebook state, outputs, plotting mechanics, and headless execution to `jupyter-notebook-review`; retain scientific interpretation of plots here.
- Route fixture/assertion mechanics and general property-test design to `python-test-quality`; retain the scientific properties and oracle independence here.
- Route benchmark runners and non-scientific fixture tooling to `python-support-scripts`.
- Route install and native-artifact packaging to `python-build-portability`.

## Review Workflow

1. State the mathematical object, expected properties, coordinate/unit conventions, and valid input domain.
2. Identify the oracle or derivation used to judge correctness.
3. Trace normal, boundary, degenerate, and non-finite inputs.
4. Assess numerical error relative to scale and conditioning.
5. Check reproducibility, data representation, and cross-language assumptions.
6. Consider performance only after correctness and with evidence proportionate to the claim.

## Mathematical And Algorithmic Validity

Check that formulas implement the intended model; orientation, indexing, units, dimensions, normalization, and boundary conventions agree; and shortcuts preserve required properties.

Exercise empty, minimal, duplicate, collinear, singular, near-degenerate, extreme-scale, and adversarial inputs as the domain requires. Flag algorithms that silently return plausible but invalid results, circular validation against the implementation, and complexity that becomes infeasible at expected sizes.

## Numerical Robustness

Check:

- tolerances follow scale, conditioning, and the quantity being compared
- exact floating equality is used only for intentionally exact values
- NaN, infinity, overflow, underflow, cancellation, and invalid casts are deliberate
- dtype and precision choices preserve the required range and accuracy
- reductions and order-sensitive calculations behave acceptably across supported environments
- clipping, coercion, fallback values, and warning suppression do not hide scientific failure

Require a reason for fixed epsilon values and loose tolerances. Prefer stable formulations over compensating with wider tests.

## Independent Evidence

Prefer scientific checks that do not merely repeat the implementation:

- conservation, symmetry, monotonicity, topology, normalization, or other invariants
- trusted small cases with hand-derived results
- metamorphic relations and transformations
- an independent algorithm or external reference implementation
- property-based generation constrained to meaningful domains
- regression fixtures for discovered counterexamples

State what the oracle can and cannot prove. Cross-checking Python against native code is weak when both share the same formula, fixture generator, or mistaken convention.

## Stochastic And Reproducible Behavior

Use explicit random-generator objects and recorded seeds. Distinguish deterministic regression tests from statistical tests. Check sample-size justification, estimator bias, variance, convergence diagnostics, burn-in/thinning assumptions, and multiple-comparison effects where applicable.

Ensure ordering, file names, precision, metadata, and generated artifacts are stable. Avoid dependence on global random state, timestamps, unsorted input, ambient threads, locale, or current working directory.

## Data And Interoperability Contracts

Verify schemas, column meaning, missing values, units, coordinate order, indexing base, dimension order, dtype, precision, endianness, delimiters, and versioning across producers and consumers.

When Python validates Rust, C++, or another native component, keep the Python path independent enough to catch native defects. Ensure subprocess failures preserve useful diagnostics and generated fixtures remain stable when they are semver- or publication-relevant.

## Performance Claims

Flag obvious accidental quadratic work, repeated large copies, per-row dataframe operations, and unnecessary I/O in hot paths. Prefer vectorization only when it preserves clarity and numerical meaning. Require representative benchmarks before claiming improvement; do not turn a correctness review into speculative micro-optimization.

## Output

Lead with mathematical, numerical, reproducibility, or interoperability blockers. For each finding, state the violated property, triggering input class, consequence, smallest correction, and independent evidence needed. Report assumptions, focused skills handed off, validation run, and unavailable datasets or platforms.
