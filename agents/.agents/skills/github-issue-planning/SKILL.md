---
name: github-issue-planning
description: "Plan or update GitHub issue dependencies, milestones, labels, and project fields when issue organization is requested."
---

# GitHub Issue Planning

Plan or update issue organization through the source of truth: native issue
dependencies, Projects v2 fields, labels, and milestones. Issue-body prose may
disagree with those records. Edit bodies only when the user requests text changes.
Keep this activity scoped to issue metadata; it does not authorize code or Git
mutations in an accompanying implementation task.

## Inspect and Plan

Identify the repository and exact issues. Read current bodies, metadata and
native dependencies, including closed prerequisites when relevant. Inspect the
project schema when custom fields own the requested relationship. Use existing
labels and preserve out-of-scope milestone and dependency decisions.

Read [metadata commands](references/github-metadata.md) when using `gh` or the
GraphQL API. Resolve owner/repository variables and paginate all relevant lists.

Represent intended ordering as directed edges: `A -> B` means B is blocked by A.
Check direction, duplicate edges, and cycles before applying the smallest change.
Do not create dependency cycles. If the proposed plan has one, explain it and
resolve the intended ordering before editing those edges. Related work that can
proceed together does not require mutual blocking.

## Apply and Verify

Apply authorized changes using native metadata operations. Re-query affected
issues and verify actual dependencies, fields, labels, milestones, or text.
Report the resulting order, concrete changes, and any unresolved discrepancy.
Existing authorization remains valid for the same action and scope across turns;
reading metadata and preparing a concrete plan need no additional confirmation.
