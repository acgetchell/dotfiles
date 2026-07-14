# Repository-Owned Static Analysis Review

Use this reference for Semgrep, Opengrep, or similar repository-owned rule
configuration and fixtures.

## Ownership

- Identify the narrow invariant each rule owns before editing it.
- Do not duplicate a structured parser or domain validator with a weaker text
  rule. Let parsers own schema, type, uniqueness, and graph invariants; use
  static analysis for recognizable policy-breaking source patterns.
- Preserve an existing rule ID when broadening the same invariant so SARIF
  history and suppressions remain stable. Introduce a new ID for a genuinely
  different policy.

## Rule Design

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

## Fixtures

- Add at least one `ruleid` case for each new behavior and one `ok` case for the
  closest approved form.
- Exercise meaningful variants, such as single-line/multiline syntax, canonical
  paths, generated IDs, or direct versus parameterized destinations.
- Use the annotation syntax recognized by the fixture harness even when the
  fixture's native comment syntax differs.

## Validation

Run these layers in order when the repository provides them:

1. configuration/schema validation
2. the focused fixture suite
3. the real repository scan to detect false positives
4. the repository's matching configuration/documentation validators

Do not treat fixture success as sufficient: a rule can match its synthetic case
and still be too broad for real code. Conversely, do not remove a useful rule
only because an unrelated pre-existing violation exists; narrow paths or migrate
the baseline deliberately.
