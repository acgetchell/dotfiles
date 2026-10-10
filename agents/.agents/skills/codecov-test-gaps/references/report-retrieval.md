# Coverage Report Retrieval

## Confirm the coverage setup

Start by inspecting the repository:

- discover coverage workflows in `.github/workflows/` by their coverage/upload steps
- read the workflow to identify test commands, coverage tool invocation, artifact/report names, upload steps, flags, and paths
- check for `codecov.yml`, `.codecov.yml`, and coverage reports or artifacts such as `coverage.xml`, `lcov.info`, or HTML coverage output
- identify the language test framework from project files instead of assuming one

Use the discovered workflow name in commands; do not assume it is named `codecov.yml`.

## Fetch the relevant Codecov context

Pick the report that matches the task. Prefer most-specific to least-specific:

1. **Open PR for the current branch.** This is the right view for release-prep work because Codecov highlights patch coverage and the project delta against the base.
   - `gh pr view --json number,headRefName,headRefOid,statusCheckRollup,comments,url`
   - read the Codecov bot comment for patch coverage, project delta, and per-file gaps
   - `gh api repos/:owner/:repo/commits/<sha>/status` for the Codecov status check
2. **Latest completed branch run.** Use this when there is no PR yet.
   - `gh run list --workflow <coverage-workflow> --branch <branch> --limit 5 --json databaseId,status,conclusion,headBranch,headSha,displayTitle,createdAt,url`
3. **Latest completed run of the discovered coverage workflow.** Fall back to this when the task is not branch-specific.

For the chosen run:

- inspect with `gh run view <run-id> --log` and `gh run view <run-id> --json jobs,conclusion,url`; request additional JSON fields only after confirming `gh run view --json` supports them in the installed CLI
- download coverage artifacts with `gh run download <run-id> --dir <tmp-dir>` when artifacts exist (for example `coverage.xml`, `lcov.info`, or a named coverage artifact)
- record the commit SHA the report was generated from so findings reference the right code

Do not require or print Codecov tokens. If a private Codecov report cannot be accessed, rely on workflow artifacts/logs and ask the user for a report link only if necessary.
