# Standalone Review Workflow

Read only for direct invocation without a parent scope and result contract.
Read [standalone discovery](../../rust-review-orchestrator/references/standalone-discovery.md),
then apply this skill's complete domain checklist.

## Output Format

### Scope

- State whether the review covers changed APIs, a specific public workflow, or a broader API baseline.

### Summary

- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings

- Ordered by impact.
- Include file and line references.
- Explain whether the issue is workflow order, hidden mutation, redundant public surface, lost validation evidence, or public-sample ergonomics.

### Suggested Fixes

- Give concrete method/type names and the intended chain shape.
- Name tests or examples that should change.

### Optional Improvements

- List non-blocking ergonomic polish separately from correctness or API-surface concerns.
