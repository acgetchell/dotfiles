# Standalone Review Workflow

Read only for direct invocation without a parent scope and result contract.
Read [standalone discovery](../../rust-review-orchestrator/references/standalone-discovery.md),
then apply this skill's complete domain checklist.

## Scope Modes

Default mode:

- Audit newly added or modified generics, trait bounds, associated type constraints, and `where` clauses.
- Ignore unrelated unchanged bounds unless they define local generic conventions for the changed code.

Whole-repo baseline mode:

- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit public generic APIs and complex internal generic code across Rust source, tests, examples, and benches.
- Prioritize findings by downstream API ergonomics, unnecessary public bounds, leaked implementation details, duplicated constraints, and bounds that obscure ownership or Send/Sync intent.
- Do not require fixing every historical generic cleanup in one pass; separate semver-sensitive API changes from internal simplifications.

## Output Format

### Summary

- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings

- Concrete issues with file/function/type references
- For each issue, state whether the problem is redundant, misplaced, overly broad, under-specified, or public-API-hostile

### Required Fixes

- Bounds to remove
- Bounds to move from type definitions to impls/methods
- Signatures or `where` clauses to simplify
- Public API docs, doctests, or integration tests to update

### Optional Improvements

- Non-blocking readability or ergonomics refinements
