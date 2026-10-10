# GitHub Issue Metadata Commands

Use these examples for the selected repository and issue IDs. Supply both
`-f owner='<owner>' -f repo='<repo>'` to GraphQL queries declaring those variables;
never infer a repository from a copied example. For list queries, add
`pageInfo { hasNextPage endCursor }`, pass an `after` cursor, and continue until
`hasNextPage` is false. Paginate nested dependency, label, and project lists as
well, or query the affected issues individually. A fixed `first` limit is not
proof of completeness. REST list endpoints may use `gh api --paginate`.

For native dependencies, `issueId` is blocked and `blockingIssueId` is its
prerequisite. Inspect current API support when a field is unavailable; never
silently substitute body text for native metadata.

## Example 1

```bash
gh issue view <number> --json number,title,body,labels,milestone,projectItems,url
```

## Example 2

```bash
gh api graphql -f owner='<owner>' -f repo='<repo>' -f query='
query($owner:String!, $repo:String!, $after:String) {
  repository(owner:$owner, name:$repo) {
    issues(first:100, after:$after, states:OPEN) {
      pageInfo { hasNextPage endCursor }
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

## Example 3

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

## Example 4

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

## Example 5

```bash
gh api --paginate 'repos/:owner/:repo/labels?per_page=100' --jq '.[] | {name,description,color}'
gh api --paginate 'repos/:owner/:repo/milestones?state=all&per_page=100' --jq '.[] | {number,title,state,due_on}'
```

## Example 6

```bash
gh api graphql -f owner='<owner>' -f repo='<repo>' -f query='
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
