# Platform Coverage And Native CI

Apply this gate to PR reviews and to changes whose behavior depends on a
supported operating system. The coordinator owns discovery and closure;
specialists own diagnosis; validators own execution. Do not infer platform
coverage from a skill name.

## Discover Before Routing

Read the repository's support policy and CI workflows, including unchanged
workflows that execute changed code or tests. Record the supported OS, Python,
shell, and relevant dependency combinations. Distinguish the local executor
from the target matrix. `package = false` does not remove portability concerns.

When changed Python scripts, tests, fixtures, or command configuration run on
Windows, select these existing owners as applicable, even without packaging
or workflow edits:

| Owner | Required review |
|---|---|
| `python-build-portability` | Platform-sensitive source and fixture assumptions; read its `references/windows-boundaries.md` |
| `python-support-scripts` | Support-script and shell/subprocess boundaries; read its `references/platform-subprocess-evidence.md` |
| `python-test-quality` | Changed tests/fixtures or a native regression; read its `references/platform-regression-evidence.md` |
| `project-tooling-review` | Workflow, shell, environment, or command wiring when those contracts are implicated |

Use semantic routing overrides for relevant paths outside catalog patterns.
An unchanged workflow may supply context without broadening the change scope.
Preserve shared ownership: running pytest does not replace source portability
review, and a packaging audit does not replace fixture review.

Put applicable reference paths in routing records' `static_references` so they
reach the materialized dispatch. Workers must read their `SKILL.md` and those
references before inspecting the boundary,
and record actual reads in `nearby_contract_owners`. Before accepting their
reports, check for those reads and concrete boundary evidence in findings or
the reviewed files/coverage units. Missing reads require completing that pass;
do not retroactively claim a reference informed a review.

## Inspect Native CI At Start And Before Closure

Resolve an associated PR for branch reviews; absence of a supplied PR number
does not establish that no PR exists. For a PR, actively retrieve its current
head and check results; do not wait for the user to point out a failing job.
Read-only GitHub CLI examples:

```sh
gh pr view <PR> --repo <owner/repo> --json url,headRefOid,statusCheckRollup
gh run view <run-id> --repo <owner/repo> --json headSha,event,attempt,status,conclusion,jobs,url
gh run view <run-id> --repo <owner/repo> --attempt <attempt> --job <job-id> --log-failed
```

Inspect every failing job, explicitly including Windows when it is in the
supported matrix. Fetch the relevant failed-step logs; a red summary alone
does not explain the failure. Include required jobs and jobs exercising the
changed surfaces, even if branch protection does not require them. Check
legacy status contexts through their provider when they are not Actions jobs.

Keep the raw results/logs in the external proof store. Record retrieval time,
PR head, tested SHA (and head/merge-ref relationship), run attempt, job URL,
actual runner OS/shell, conclusion, failed step, and owning review disposition.
For failed or missing cells, preserve an explicit native validation requirement
and `validation_limits` entry; do not substitute the current host's platform.
Refreshing status is not permission to push, rerun CI, or modify workflow policy.

Uncommitted fixes have no remote result for their exact bytes. Older CI is
diagnostic history, not validation of those fixes. Likewise, when the PR head
changes, reconcile the new source and refresh evidence before closure. A PR
merge-ref run must be related to the reviewed head and base before reuse.

If authentication, network, missing runs, pending jobs, cancelled jobs, or
unavailable logs prevent inspection, retain a concrete gap. Do not call an
empty check list a pass. For a local-only review without a PR, record that
remote CI is not applicable and retain any required native platform gaps.

## Close Only With Reconciled Evidence

Supply the CI observations through accepted owning review/validation records
before repository synthesis. Validators must receive exact commands and
target obligations; syntheses must not discover CI on their own. Route each
failure to its source, test, or tooling owner. Preserve failures until a
diagnosis and current native result reconcile them; local or emulated success
cannot resolve a Windows failure. An unrelated failure needs an evidence-backed
disposition and remains visible as a failed CI result.

Before saying the review is complete, verify:

- Applicable skills and platform references were actually read and applied.
- Current PR checks were inspected, every failure has an owning disposition,
  and required native validation is represented in the evidence ledger.
- Final synthesis preserves failed, stale, pending, unavailable, and unexecuted
  cells in `validation_reconciliation` when accepted validator evidence exists,
  and in `cross_surface_risks`/`verdict_reasons` for remaining gaps. Never invent
  validator evidence IDs for a status observation.

A review-only report may finish with diagnosed findings and `not-ready`;
that does not mean CI passed. Missing inspection or required evidence means
`blocked`, even if a narrower graph proof is structurally complete. In
review-and-fix work, a locally corrected native failure remains unverified
until current native CI passes. Report that distinction explicitly; do not
claim all fixes verified or the PR ready while that obligation remains open.
