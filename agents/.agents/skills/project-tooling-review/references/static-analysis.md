# Static-Analysis Policy And Effectiveness

Use this reference to evaluate and maintain Clippy lint policy, selected Semgrep
rules, repository-owned rules, and their effective coverage. Apply changes when
the user requests maintenance or fixes; keep an audit read-only. A graph dispatch
still controls scope, edit authorization, and assigned validation.

## Inventory And Decisions

Inspect the relevant configuration, source suppressions, fixtures, and actual
local and CI invocations. Record tool versions and configured engines, enabled
groups or rulesets, severity and failure behavior, and includes and exclusions.
Distinguish configured checks from checks that actually execute and enforce a
policy. Use documentation matching the installed or pinned version when
evaluating available lints, deprecated names, or engine capabilities.

For each proposed change or questionable check, identify the protected policy,
relevant source examples, and evidence for one of these decisions. Group
unchanged defaults rather than producing an exhaustive lint catalog.

| Decision | Evidence |
| --- | --- |
| Keep | A relevant risk or convention with useful detection and acceptable noise. |
| Add | An uncovered project concern, recurring review finding, or past defect with a reliably detectable pattern. |
| Adjust | A useful check with incorrect scope, severity, configuration, suppressions, or detection behavior. |
| Remove | An obsolete policy, a superseding check with demonstrated coverage, or noise and maintenance cost that outweigh its remaining benefit. |

Zero findings alone never justify removal: a clean baseline can be the desired
result of a useful regression guard. Check whether the governed API, construct,
or policy still exists and whether future violations remain plausible. Before
removing a duplicate, demonstrate that its replacement detects representative
violations under the real scan configuration. Prefer narrowing a noisy check
when its underlying protection remains valuable. Preserve intentional policy
exceptions and record unresolved tradeoffs instead of silently weakening gates.

## Ownership

- Identify the narrow invariant each rule owns before editing it.
- Prefer an existing compiler or Clippy lint, including supported configuration,
  when it adequately enforces the policy. Use Semgrep for project-specific
  patterns that need additional protection; do not assume similarly named
  checks have equivalent semantics or scope.
- Do not duplicate a structured parser or domain validator with a weaker text
  rule. Let parsers own schema, type, uniqueness, and graph invariants; use
  static analysis for recognizable policy-breaking source patterns.
- Preserve an existing rule ID when broadening the same invariant so SARIF
  history and suppressions remain stable. Introduce a new ID for a genuinely
  different policy.
- Keep Cargo declaration and release compatibility under `rust-cargo-hygiene`,
  and supported build-configuration correctness under `rust-build-portability`.
  This reference owns cross-tool policy usefulness and enforcement coverage.
- Treat application line and branch coverage as supporting evidence, distinct
  from static-analysis coverage. Route requests to fill application test gaps
  to `codecov-test-gaps` and the appropriate language test-quality skill. Under
  graph dispatch, report those needs as handoffs rather than loading skills.

## Rust And Clippy

- Inspect `[workspace.lints]`, member `[lints]` inheritance, crate and item
  attributes, `clippy.toml` or `.clippy.toml`, and command-line overrides.
  Confirm member opt-in and effective lint levels, including group priorities;
  a workspace declaration alone does not prove enforcement in every member.
- Separate the toolchain running Clippy from the library's supported MSRV.
  Check new lint availability on the linting toolchain and whether proposed
  fixes remain compatible with the MSRV. Do not upgrade toolchains merely to
  enable more lints unless that change is in scope.
- Evaluate optional lints against real code and project policy. Never enable
  the entire `clippy::restriction` group; its lints can conflict. Consider
  `pedantic` and `nursery` noise and stability before extending existing policy.
- Review broad `allow` attributes and `expect` annotations for continued
  justification and narrow scope. Where supported, unfulfilled expectations
  can expose stale exceptions; absence of that warning is not proof of value.
- Consider Clippy's configurable disallowed APIs before writing a parallel
  Semgrep prohibition. Check legitimate test, example, benchmark, and generated
  code use before imposing a crate-wide restriction.

Consult [Clippy configuration](https://doc.rust-lang.org/stable/clippy/configuration.html),
[lint groups](https://doc.rust-lang.org/stable/clippy/usage.html), and
[Cargo lint inheritance](https://doc.rust-lang.org/cargo/reference/workspaces.html#the-lints-table)
as needed; verify behavior against the repository's toolchain.

## Coverage

Report these dimensions separately; rule counts or a clean scan do not establish
completeness:

- **Execution:** which packages, paths, Cargo targets, feature configurations,
  and platforms are actually analyzed. Inspect ignores, suppressions, disabled
  jobs, differential-only scans, parser failures, timeouts, and skipped files.
  For Rust, `--all-targets` does not cover every target triple or `cfg` branch,
  and `--all-features` does not replace supported minimal or curated feature
  configurations. Use the repository's supported matrix, not every possible
  combination.
- **Detection:** whether known violations trigger the intended rule and nearby
  compliant cases pass. Use fixtures and representative mutation pairs; list
  known misses and unsupported syntax. Verify relevant Rust macros, aliases,
  and type-sensitive cases against the configured Semgrep engine instead of
  assuming compiler-equivalent resolution.
- **Policy:** map important in-scope concerns to existing checks, candidate
  checks, or tests and human review where static analysis is unsuitable.
  Prioritize demonstrated risks; do not invent a percentage of all possible
  defects covered.

## Semgrep Rule Design

- Prefer AST-aware language rules for source semantics and bounded regex or
  generic rules for serialized/configuration text.
- Keep path includes and excludes explicit, especially for deliberate violation
  fixtures that normal repository scans must ignore.
- Bound multiline patterns to the smallest useful construct. Avoid patterns that
  can drift across unrelated cells, documents, jobs, or declarations.
- Use YAML block scalars deliberately. Strip the trailing newline with `|-` when
  it is not part of the intended regex.
- Keep messages actionable: identify the approved replacement, owner, or
  workflow rather than only naming the forbidden pattern.

## Semgrep Fixtures

- Before editing a text or regex rule, inventory its in-scope corpus for
  structurally distinct forms of the governed construct. Include representations
  such as mapping keys versus sequence-item shorthand, single-line versus
  multiline forms, and direct versus parameterized values when they exist. Do
  not assume the current fixtures exhaust the repository's syntax.
- For each supported structural form, derive a fixture from a compliant corpus
  example and minimally mutate only the governed value into a violation. Require
  the applicable `ruleid` on the mutation and retain the compliant form as an
  `ok` case. This mutation pair must prove that the rule observes the syntax, not
  merely that the valid example produces no finding.
- Add at least one `ruleid` case for each new behavior and one `ok` case for the
  closest approved form.
- Exercise meaningful variants, such as single-line/multiline syntax, canonical
  paths, generated IDs, or direct versus parameterized destinations.
- Use the annotation syntax recognized by the fixture harness even when the
  fixture's native comment syntax differs.
- Track expected misses separately from passing detection evidence. Semgrep's
  `todoruleid` and `todook` annotations do not fail the test suite. If a rule
  supplies an autofix, verify the resulting code as well as finding locations;
  see [Semgrep rule testing](https://semgrep.dev/docs/writing-rules/testing-rules).

## Validation

Use repository recipes for the relevant layers, within the assigned validation
scope:

1. configuration/schema validation
2. the focused Semgrep fixture suite or representative Clippy policy probes
3. the real repository scan or Clippy invocation to detect false positives and
   verify execution scope
4. the repository's matching configuration/documentation validators

For a material Clippy policy change, use a temporary or existing fixture crate
when needed to prove the effective configuration catches the intended diagnostic
and permits the approved alternative. Do not recreate Clippy's upstream test
suite or introduce deliberate violations into production code. Check command
exit behavior when CI enforcement changes. Keep Semgrep fixture matching and
production path-filter enforcement distinct; an annotation test alone need not
exercise the paths used by the actual scan.

Treat a clean real-repository scan as false-positive evidence only. Unless the
corpus contains a deliberate known violation, it cannot prove that the rule
would detect a violation written in the same structural form.

Do not treat fixture success as sufficient: a rule can match its synthetic case
and still be too broad for real code. Conversely, do not remove a useful rule
only because an unrelated pre-existing violation exists; narrow paths or migrate
the baseline deliberately.

## Report

Summarize keep/add/adjust/remove decisions with policy rationale, affected scope,
and validation evidence. Report execution, detection, and policy gaps separately,
including unexecuted configurations and known tool limitations. Record useful
deferred checks and application-test handoffs; do not claim unmeasured coverage.
