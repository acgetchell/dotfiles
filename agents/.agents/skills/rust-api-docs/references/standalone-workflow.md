# Standalone API Documentation Review

Read this reference only when `rust-api-docs` is invoked directly without an
exact parent scope and result contract. Review-graph and Rust-orchestrator
dispatches already own scope and reporting.

## Scope Modes

In default mode, audit newly added or modified public APIs. Ignore unrelated
unchanged APIs unless they clarify the changed contract.

Use whole-repository baseline mode only when the user explicitly requests a
whole-repository or baseline audit. Cover crate and module docs, public items,
examples, rustdoc lint configuration, and docs.rs metadata. Prioritize
published API risk, broken or missing required sections, misleading contracts,
and examples users are likely to copy. Group lower-risk historical gaps as
follow-up work instead of requiring all of them in one patch.

## Standalone Report

Classify the result as `PASS`, `NEEDS IMPROVEMENT`, or `FAIL`. Report:

- public items missing required sections or useful descriptions
- broken links, import paths, examples, and API-supporting helper documentation
- required section, link, description, helper-comment, lint, or docs.rs fixes
- optional example and cross-link improvements
