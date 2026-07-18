---
name: github-issue-planning
description: "Plan and maintain GitHub issues using native dependency metadata, Projects v2 fields, labels, and milestones. Use for ordering work, Blocking/Is blocked by relationships, dependency cycles, milestone triage, roadmap sequencing, and project metadata. Do not edit code or substitute body prose for native metadata."
---

# github-issue-planning

Maintain GitHub issue planning metadata as metadata, not prose. Native issue
dependencies, Projects v2 fields, labels, and milestones can disagree with issue
bodies; inspect the source of truth before editing.

## Workflow

### 1. Identify the repository and intended plan

- Confirm the GitHub owner/repo from `gh repo view --json owner,name,url` or the
  issue URLs in the task.
- Read the user-requested order as a graph, not just a list.
- If the user mentions "blocked", "blocking", "is blocked by", or issue
  ordering, assume native GitHub issue dependencies may be involved.

Use `gh` only for repository and issue metadata, including the dependency,
label, and milestone operations described below. Do not edit code. Do not edit
issue bodies or substitute body prose for native metadata unless the user
explicitly asks for text changes.

### 2. Inspect current issue metadata

Start with read-only issue context:

```bash
gh issue view <number> --json number,title,body,labels,milestone,projectItems,url
```

Then query native dependencies with GraphQL. `gh issue view` may omit native
dependency edges.

```bash
gh api graphql -f query='
query($owner:String!, $repo:String!) {
  repository(owner:$owner, name:$repo) {
    issues(first:100, filterBy:{states:OPEN}) {
      nodes {
        number
        title
        id
        milestone { title }
        labels(first:20) { nodes { name } }
        blockedBy(first:20) { nodes { number title id state } }
        blocking(first:20) { nodes { number title id state } }
        issueDependenciesSummary {
          blockedBy
          blocking
          totalBlockedBy
          totalBlocking
        }
        projectItems(first:20) {
          nodes { id project { title } }
        }
      }
    }
  }
}'
```

If the repo has many issues, query specific issue numbers individually instead
of loading all open issues.

### 3. Distinguish dependency systems

GitHub has multiple planning surfaces:

- Native issue dependencies: `Issue.blockedBy` and `Issue.blocking`.
- Projects v2 item fields: custom fields such as "Status", "Priority",
  "Blocking", or "IsBlocked" on project items.
- Issue body prose: markdown such as `Depends on: #60`.

Do not substitute one for another. If the user says the relationship is in
`Blocking` or `IsBlocked`, inspect GraphQL native issue fields and Projects v2
item fields before deciding which surface to update.

### 4. Plan minimal graph mutations

Represent the intended order as edges:

```text
#60 -> #61 -> #59
```

means:

- `#61` is blocked by `#60`
- `#60` is blocking `#61`
- mutation input: `issueId = #61`, `blockingIssueId = #60`

Before mutating:

- remove inverted edges
- avoid duplicate edges
- avoid cycles unless the user explicitly wants to model mutual blocking
- preserve closed blockers when they document completed prerequisite work unless
  the user asks to clean them up
- preserve downstream blockers that are outside the requested reorder

### 5. Mutate native dependencies

Use `addBlockedBy` and `removeBlockedBy`. The direction is easy to invert:

- `issueId` is the blocked issue
- `blockingIssueId` is the issue that must happen first

Add a blocker:

```bash
gh api graphql \
  -f query='mutation($issue:ID!, $blocking:ID!) {
    addBlockedBy(input:{issueId:$issue, blockingIssueId:$blocking}) {
      issue { number blockedBy(first:20) { nodes { number } } }
    }
  }' \
  -f issue='<BLOCKED_ISSUE_NODE_ID>' \
  -f blocking='<BLOCKING_ISSUE_NODE_ID>'
```

Remove a blocker:

```bash
gh api graphql \
  -f query='mutation($issue:ID!, $blocking:ID!) {
    removeBlockedBy(input:{issueId:$issue, blockingIssueId:$blocking}) {
      issue { number blockedBy(first:20) { nodes { number } } }
    }
  }' \
  -f issue='<BLOCKED_ISSUE_NODE_ID>' \
  -f blocking='<BLOCKING_ISSUE_NODE_ID>'
```

Apply the smallest set of mutations that turns the current graph into the
requested graph.

### 6. Handle labels and milestones

Inspect existing labels and milestones before editing:

```bash
gh label list --limit 200
gh api repos/:owner/:repo/milestones --jq '.[] | {number,title,state,due_on}'
```

Rules:

- Reuse existing labels; do not invent new labels unless the user asks.
- Keep labels orthogonal: feature area, language, docs/testing/API, priority,
  and release status should each be represented separately if the repo already
  uses them.
- Issues in a deliberate sequence should usually share a milestone when they are
  part of the same release train.
- Do not move issues into a milestone if the issue body says the work is
  explicitly post-release or downstream-only.

Use `gh issue edit` for labels and milestones after confirming the intended
change.

### 7. Verify and report

After edits, re-query all affected issues:

```bash
gh api graphql -f query='
query($owner:String!, $repo:String!) {
  repository(owner:$owner, name:$repo) {
    issue(number:60) {
      number
      blockedBy(first:20) { nodes { number title state } }
      blocking(first:20) { nodes { number title state } }
    }
  }
}'
```

Report:

- final order as `#A -> #B -> #C`
- dependency edges added and removed
- labels or milestones changed
- preserved relationships and why
- any ambiguity between native dependencies, Projects v2 fields, and body text

Do not claim completion until the verification query matches the intended graph.

## Safety notes

- Native dependency mutations change GitHub issue metadata immediately.
- Prefer exact issue numbers and titles in user-facing summaries.
- If a requested graph would create a cycle, stop and explain the cycle.
- If project custom fields appear to be the source of truth, inspect the project
  schema and item IDs before editing them.
- Do not touch local git state for issue-planning tasks.
