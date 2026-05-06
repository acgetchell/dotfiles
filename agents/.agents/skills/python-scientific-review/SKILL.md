---
name: python-scientific-review
description: "Perform rigorous senior-level review of Python that implements numerical, geometric, statistical, or scientific-computing logic alongside a Rust crate on changed code or whole-repo baseline audits when explicitly requested. USE FOR: Python that implements numerical/geometric/statistical/topological algorithms, validates Rust numerical output, checks reproducibility of scientific results, generates scientific fixtures (point clouds, meshes, distributions), audits NumPy/SciPy correctness, reviews Hypothesis property tests over numerical inputs, or checks Rust interoperability for numerical formats (coordinates, indexing, dtypes). DO NOT USE FOR: changelog generators, benchmark runners, release helpers, CI scripts, fixture/diagnostic CLIs, or other Python support tooling (use python-support-scripts); general Python web/app code; formatting-only cleanup; Rust code review (use rust-production-review or other Rust skills); or unrelated unchanged code unless a baseline audit is requested."
---

# python-scientific-review

Review Python scripts and tests in scientific computing repositories with the same engineering discipline expected from production Rust: explicitness, safety, invariants, reproducibility, and numerical correctness.

These scripts often validate Rust crates, generate datasets, run benchmarks, or diagnose numerical behavior. Convenience is secondary to correctness and reproducibility.

## Scope

Focus on newly added or modified Python code that:

- implements numerical, geometric, topological, statistical, or linear algebra logic
- cross-checks Rust numerical output for correctness
- generates scientific fixtures (point clouds, meshes, distributions, reference data)
- tests scientific algorithms or invariants over generated inputs
- uses NumPy, SciPy, pandas, matplotlib, or Hypothesis on numerical data
- reads or writes numerical files consumed by the Rust crate (coordinates, dtypes, indexing)

If the Python is dev tooling (changelog generators, benchmark runners, release helpers, CI scripts, diagnostic CLIs that don't implement numerical logic), use `python-support-scripts` instead.

Ignore unrelated unchanged code unless needed to understand data formats, invariants, or Rust interoperability.

### Scope Modes

Default mode:
- Review newly added or modified scientific Python, numerical fixtures, tests, and Rust cross-check scripts.
- Ignore unrelated unchanged scientific code unless it defines the data format or invariant used by the changed code.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit all scientific Python scripts, tests, fixtures, generated reference data paths, and Rust interoperability assumptions.
- Prioritize findings by numerical correctness, reproducibility, malformed/degenerate input handling, fixture realism, dtype/indexing compatibility, and weak invariant tests.
- Do not require fixing every historical scientific-code issue in one pass; separate correctness risks from cleanup.

## Review posture

Be direct and critical. Assume the author understands Python and Rust. Do not explain basic Python syntax or generic style rules. Focus on issues that affect correctness, reproducibility, diagnostics, maintainability, or compatibility with the Rust crate.

## Review goals

### 1. Correctness and numerical stability

Treat numerical behavior as a correctness issue.

Check:

- floating-point comparisons, tolerances, and rounding are justified by scale and algorithmic context
- algorithms handle NaN, infinity, overflow, underflow, cancellation, and precision loss
- degenerate inputs are handled explicitly
- failures are loud rather than silently producing invalid output
- platform-dependent behavior is understood and acceptable

Flag:

- naive `==` comparisons on floats unless exact equality is intended
- fixed epsilons reused across unrelated scales
- unchecked `np.nan`, `np.inf`, overflow, or invalid casts
- silent clipping, coercion, or fallback values that hide invalid data
- tests that only use well-conditioned numeric examples

### 2. Algorithmic soundness

Verify that the scientific or geometric algorithm is the right algorithm and is implemented correctly.

Check:

- formulas match the intended math
- coordinate systems, orientation conventions, indexing bases, and units are consistent
- complexity is appropriate for expected dataset sizes
- vectorization or NumPy broadcasting would improve clarity or reliability
- algorithmic shortcuts do not invalidate edge cases

Flag:

- accidental O(n^2) or worse behavior on benchmark/data-generation paths
- manual Python loops over large arrays where NumPy would be clearer and safer
- geometry logic that ignores collinearity, duplicate points, boundaries, or near-degeneracy
- sorting or grouping logic that depends on unstable or implicit ordering

### 3. Testing quality

Tests should validate invariants, not just outputs.

Check:

- tests cover edge cases: empty inputs, degenerate geometry, collinearity, duplicates, extreme values, non-finite values, and boundary sizes
- assertions are meaningful and specific
- tests validate invariants and conservation properties
- property-based tests with Hypothesis would catch broad input classes
- regression tests exist for discovered failures

Flag:

- superficial assertions such as only checking shape, non-empty output, or no exception
- tests that duplicate implementation logic without independent validation
- missing tolerances or overly loose tolerances
- randomized tests without deterministic seeds
- generated data that is too clean to reveal numerical bugs

### 4. Reproducibility and determinism

Scientific scripts should be reproducible across runs and as portable as practical.

Check:

- all randomness is explicitly seeded
- NumPy random generation uses explicit `Generator` instances where possible
- unordered containers do not affect output order
- parallel execution does not change results nondeterministically
- generated outputs have stable ordering, formatting, precision, metadata, and file names
- external inputs and environment assumptions are documented or pinned

Flag:

- global random state used implicitly
- dependence on set iteration, unsorted glob results, dict order where semantic ordering matters, timestamps, locale, current working directory, or machine-specific paths
- nondeterministic BLAS/threading behavior that affects expected outputs
- tests that pass only because inputs happen to be generated in one order

### 5. Code quality and maintainability

Scientific scripts should still have clear structure and explicit contracts.

Check:

- responsibilities are separated into small, composable functions
- mathematical names are precise and domain-appropriate
- invariants and assumptions are documented near the code that relies on them
- script entry points are separated from reusable logic
- debug prints, dead code, and ad hoc local paths are removed

Flag:

- monolithic scripts mixing parsing, computation, plotting, file I/O, and assertions
- ambiguous names such as `data`, `tmp`, `stuff`, `calc`, or `process` for mathematical values
- hidden module-level side effects
- comments that restate code while omitting the invariant or formula source

### 6. Python best practices

Prefer explicit, typed, modern Python where it improves reliability.

Check:

- type hints are used for public helpers, non-trivial data structures, and script boundaries
- `pathlib.Path` is used instead of stringly `os.path` plumbing
- dataclasses, named tuples, typed dictionaries, or small classes are used for structured records when tuples/dicts become ambiguous
- global state is avoided
- exceptions include enough context to diagnose invalid inputs

Flag:

- implicit side effects at import time
- mutable default arguments
- bare `except` or swallowed exceptions
- stringly typed records with undocumented keys
- paths assembled by string concatenation

### 7. Performance

Performance is secondary to correctness, but scientific scripts should avoid obvious waste.

Check:

- hot paths are identifiable and benchmarked when relevant
- array operations avoid unnecessary copies
- large intermediate allocations are justified
- vectorized NumPy/SciPy operations would simplify or speed up loops
- I/O is batched or streamed appropriately for expected sizes

Flag:

- premature micro-optimization that reduces clarity
- repeated conversions between lists, arrays, and dataframes
- per-row pandas operations where vectorized operations are natural
- repeated parsing or file I/O inside tight loops

### 8. Interoperability with the Rust crate

Python and Rust assumptions must match exactly.

Check:

- file formats, schemas, delimiters, dtypes, endianness, precision, and missing-value conventions match Rust expectations
- coordinate conventions, orientation, indexing base, dimension ordering, and units are consistent
- generated fixtures are stable and versioned when semver-relevant
- Python validation is independent enough to catch Rust bugs rather than mirroring them
- subprocess calls to Rust tools fail loudly and capture useful diagnostics

Flag:

- Python writing floats or integers in a format Rust parses ambiguously
- one-based vs zero-based indexing mismatches
- row-major/column-major or x/y/z ordering confusion
- silently accepting extra columns, missing fields, or malformed rows
- tests that only compare Python against Rust when both share the same flawed assumption

### 9. Security and robustness

Scripts should fail safely and clearly on bad inputs.

Check:

- external input paths and file contents are validated
- shell execution is avoided or uses safe argument arrays
- output paths do not accidentally overwrite important files
- errors include file paths, row numbers, shapes, ranges, or offending values where useful
- cleanup does not delete broad or user-controlled paths

Flag:

- `shell=True` with interpolated values
- unsafe temporary file handling
- unvalidated external data
- broad deletes, overwrites, or writes outside expected output directories
- assertions used for user-input validation in scripts that may run with optimization

## Output Format

Start with a concise summary covering overall quality and major risks.

Then group findings by severity:

### 🔴 Critical (must fix)
- Correctness, reproducibility, Rust-compatibility, data-loss, or unsafe-execution issues that should block merging.

### 🟠 Important (should fix)
- Robustness, maintainability, test quality, or performance problems that should be addressed soon.

### 🟡 Improvements (nice to have)
- Non-blocking improvements that would make the code clearer, faster, or easier to maintain.

Provide concrete code suggestions where applicable. Avoid praise unless it highlights a strong pattern worth preserving.
