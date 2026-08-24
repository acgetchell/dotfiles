# Standalone Repository Documentation Workflow

Read this reference only when `repository-docs-review` is invoked directly
without an exact parent scope, validation ledger, and result contract.
Review-graph and documentation-orchestrator dispatches already own this
information.

## Scope Modes

Default to the branch or changed-file documentation surface. For an explicit
whole-repository baseline or documentation release-readiness review, inspect
every tracked active document, including unchanged files. A diff supplies
context; it does not limit a full-suite review.

## Fix And Validation

When fixes are authorized, make focused edits that preserve repository tone and
structure. Prefer extending the owning page over creating a competing page and
add required navigation entries.

Run the narrowest authoritative checks first, followed by the
repository-mandated docs or CI command. Typical checks include a docs or site
build, generated-output drift check, Markdown lint, link validation, spelling,
and configuration parsing. Do not invent a validator when the repository
already defines one. If a check needs unavailable network access or
installation, run the strongest local substitute and report the remaining gap.

## Standalone Report

Report the scope and active/generated/archive classification, documents and
authorities inspected, findings or explicit no-finding results with file-level
evidence, edits and preserved discrepancies, specialist handoffs, validators
and results, and remaining gaps or deferred work.
