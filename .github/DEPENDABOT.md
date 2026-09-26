# Dependabot approval rollout

Dotfiles calls the shared [v0.1.7 approval workflow](https://github.com/acgetchell/research-repo-tools/blob/0a02204d4a889dfc97f55286c008397ced05d6ad/.github/workflows/dependabot-approve.yml).
The pinned commit contains shared-tools PR #54; its prerequisite pilot
[PR #52](https://github.com/acgetchell/research-repo-tools/pull/52) merged on
September 26, 2026. The Python tooling package is also pinned to v0.1.7;
its registry pin and this workflow's commit pin are updated independently.
The approval workflow is unchanged between #54's merge and this release pin.

## Contract

The trusted `main` caller uses `pull_request_target` and `GITHUB_TOKEN`, with
write permissions confined to its approval job. It never checks out PR code,
executes PR scripts, or forwards personal tokens. The shared workflow verifies
same-repository Dependabot identity, signed commits, current head, metadata,
complete changed-file lists, and effective branch rules before approving.

The caller permits only `pyproject.toml` and `uv.lock` for `uv`, and the exact
three workflow paths for `github_actions`. Review the allowlist when workflows
or composite actions are added or renamed. Added, removed, renamed, or
unexpected files require manual review. Dependency names and version eligibility
belong to `.github/dependabot.yml`: patch, minor, major, grouped, and security
updates are eligible. Monday schedules, seven-day cooldowns, and groups remain
unchanged. CodeRabbit remains a separate required status check.

A verified GitHub base merge is eligible only when its parents form the expected
chain and its changed paths, statuses, and blob IDs match the original Dependabot
update exactly. Dependency conflict resolutions require manual review or a fresh
Dependabot rebase. Approval names the current head; a changed head requires a
fresh approval and stale reviews must be dismissed. Native squash auto-merge
still waits for strict `verify` and `CodeRabbit` checks and resolved threads.
The optional approval job must never become an ordinary PR's required check.

## Deploy and verify settings

Merge the caller and CI dispatch change to `main` before rollout. These payloads
are the desired settings captured from dotfiles on September 26, 2026, not a
live-state claim. Read the live settings again before applying them; preserve
any intervening changes. `main-ruleset.json` changes only the approval count
from zero to one and stale dismissal from false to true, retaining all other
rules, checks, strictness, thread resolution, and bypass actors.

```sh
gh api repos/acgetchell/dotfiles/actions/permissions
gh api repos/acgetchell/dotfiles/actions/permissions/workflow
gh api repos/acgetchell/dotfiles/actions/permissions/selected-actions
gh api repos/acgetchell/dotfiles/rulesets/17625990
gh api repos/acgetchell/dotfiles --jq '{allow_auto_merge,allow_squash_merge}'

gh api --method PUT repos/acgetchell/dotfiles/actions/permissions/selected-actions --input .github/settings/actions-selected.json
gh api --method PUT repos/acgetchell/dotfiles/actions/permissions/workflow --input .github/settings/actions-workflow-permissions.json
gh api --method PUT repos/acgetchell/dotfiles/rulesets/17625990 --input .github/settings/main-ruleset.json
```

Repeat the GETs and also inspect `repos/acgetchell/dotfiles/rules/branches/main`.
Require read-only Actions defaults, approval enabled, selected actions only,
full SHA pinning, the existing action entries plus the two additions, auto-merge
and squash enabled, and the preserved effective main rules. Do not replace the
whole Actions permissions policy to add allowlist entries.

## Hosted acceptance evidence

After deployment, use a new Dependabot PR or a fresh reopen/synchronize event.
Rerunning an old workflow run retains its original revision and cannot prove
that the new caller is deployed. Record evidence here or in issue #85 for each
of `uv` and `github_actions`:

| Evidence | Required record |
|---|---|
| Approval | PR URL, exact head SHA, `github-actions[bot]` review URL and matching `commit_id` |
| Workflow | Successful approval run URL using the deployed caller and pinned reusable workflow |
| Merge | Native squash auto-merge enabled; merge URL only after required checks and threads clear |
| Base update | Verified preserving base merge accepted; dependency-changing base merge rejected |
| Changed head/files | Stale approval dismissed; unexpected paths receive no new approval |
| Default branch | CI run URL with `headSha` equal to the actual merge commit |

A `GITHUB_TOKEN` merge may not trigger push workflows. Dispatch CI with a branch
name and verify its exact SHA:

```sh
gh workflow run ci.yml --ref main
gh run list --workflow ci.yml --event workflow_dispatch --json databaseId,headSha,status,conclusion,url
gh run view RUN_ID --json headSha,status,conclusion,url
```

If `main` advances before dispatch, that run does not validate the earlier merge.
Do not close #85 until both ecosystems and the hosted protections are evidenced.
No open Dependabot PR was available during initial implementation; hosted rollout
and merge evidence remain pending.

## Retire the old credential

After the deployed default branch no longer uses the old review-request caller,
inventory all workflow references and the Actions, Dependabot, and applicable
environment secret names. The initial inventory found the old credential in
both repository Actions and Dependabot stores. Remove only those unused
repository secrets after confirming no remaining consumer:

```sh
rg -n 'secrets\.CODERABBIT_REVIEW_TOKEN' .github/workflows
gh secret list --repo acgetchell/dotfiles --app actions
gh secret list --repo acgetchell/dotfiles --app dependabot
gh api repos/acgetchell/dotfiles/environments --jq '.environments[].name'
gh secret delete CODERABBIT_REVIEW_TOKEN --repo acgetchell/dotfiles --app actions
gh secret delete CODERABBIT_REVIEW_TOKEN --repo acgetchell/dotfiles --app dependabot
```

Inventory any returned environment with `gh secret list --env NAME` before
removing an unused environment copy. Do not revoke the underlying credential or
remove another repository's copy. No personal token is needed by the replacement.
