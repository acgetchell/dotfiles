# Repository-Owned Static Analysis Review

Use this reference for repository-owned Semgrep rule configuration and fixtures.

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

## Validation

Run these layers in order when the repository provides them:

1. configuration/schema validation
2. the focused fixture suite
3. the real repository scan to detect false positives
4. the repository's matching configuration/documentation validators

Treat a clean real-repository scan as false-positive evidence only. Unless the
corpus contains a deliberate known violation, it cannot prove that the rule
would detect a violation written in the same structural form.

Do not treat fixture success as sufficient: a rule can match its synthetic case
and still be too broad for real code. Conversely, do not remove a useful rule
only because an unrelated pre-existing violation exists; narrow paths or migrate
the baseline deliberately.
