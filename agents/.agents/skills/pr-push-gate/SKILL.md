---
name: pr-push-gate
description: "Prepare an initial or corrective PR push by completing local security, full CI, and CodeRabbit CLI review before publishing changes."
---

# PR Push Gate

Apply before pushing a branch intended for a PR or updating an existing PR.
Batch corrections locally so each push carries validated, reviewed changes
and avoids spending hosted CodeRabbit reviews on incomplete fixes.

## Establish the outgoing scope

- Read repository instructions and inspect the current branch, intended base,
  staged and unstaged changes, and non-ignored untracked files. Preserve user work.
- For an existing PR, inspect the current remote head's workflow jobs, check
  runs, commit statuses, security findings, and unresolved review threads.
  Collect completed results before choosing the corrective batch; wait for
  outstanding checks and reviews before pushing unless the user explicitly
  directs otherwise. A successful security workflow can still have a failing
  security-results check.
- Verify findings against current code and fix valid issues together. Preserve
  the regression contract. Explain findings that do not warrant a change.
- Finish formatting and all intended edits before final validation and review.

## Complete all three local gates

1. Run `just security` and require a successful exit.
2. Run `just ci` and require a successful exit. Focused tests and `just check`
   support iteration but never replace this gate, even for one-line CI fixes.
3. Complete a local CodeRabbit CLI review through the repository's `just review`
   recipe against the actual PR base. Include the outgoing branch changes and
   any intended uncommitted changes. `just review-uncommitted` alone is
   insufficient when outgoing committed changes have not been reviewed.

Use the existing RRT recipes where available; do not duplicate their orchestration
or silently substitute narrower commands. If a required recipe or tool is
missing, report that limitation and hold the push instead of declaring it passed.
Independent validation commands may overlap when they do not interfere. Keep
reviewed source and configuration stable while CodeRabbit runs.

Require a complete review result. Authentication failures, missing completion,
unreviewed files, interruptions, and paid-consent requests are not completed
reviews. Reuse or incremental review is acceptable only when its retained
coverage and content identity establish review of the final outgoing diff;
do not claim that a reused result is a fresh review.

Verify local review findings, address valid ones, and explain any rejected
findings. After edits, formatting, conflict resolution, or rebasing, refresh
the gates for the resulting content before pushing. Never push while a gate
is still running or treat a previous version's successful checks as current.

## Preserve paid-review consent

Follow the shared [CodeRabbit paid-review rules](../../AGENTS.md#coderabbit-paid-review-consent).
Start without `--use-credits`. Stop on `action_required` or
`awaiting_confirmation`; a requirement to obtain review is not consent to buy it.
Do not add `--fresh` or `--gate` merely to bypass reuse or missing evidence.
Report the provider's actual scope and quote, including unknown terms, and
leave paid execution to the maintainer as required by the shared policy.
Complete independent CI and security work while review is blocked, but do not push.

## Publish once the gates are satisfied

Record the repository, branch/base, reviewed content, commands and outcomes,
and any findings disposition in the task's validation notes. Before pushing,
inspect the intended diff again and confirm that these results cover its final
content and that no intervening edits or base changes invalidated them.
Committing already validated content is not itself a source change.

Git authorization remains separate: the skill does not authorize staging,
commits, pushes, merges, or repository-setting changes. Use existing task
authorization where it covers the operation. Push the completed batch once,
then inspect required hosted checks on the new head before claiming merge
readiness. Local gates complement native CI; they do not prove another OS passed.

These instructions guide agent behavior; they are not a technical Git hook or
a guarantee against raw CLI bypasses.
