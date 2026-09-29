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

### Verified rollout: September 28, 2026

The caller was deployed by [PR #86](https://github.com/acgetchell/dotfiles/pull/86)
at `43ea646a2f526c8ba1545bed01b9070a314d0701`. Its ordinary-PR
[CI](https://github.com/acgetchell/dotfiles/actions/runs/36279915632) and
[default-branch CI](https://github.com/acgetchell/dotfiles/actions/runs/36280315217)
passed. Live settings were read again on September 28 (Pacific time):

- Actions defaults remain read-only; Actions approval, native auto-merge, and
  squash merging are enabled.
- Selected actions and full SHA pinning remain enforced. The allowlist matches
  `settings/actions-selected.json`, including the two shared-workflow entries.
- Ruleset `17625990` and the effective `main` rules require one approval, stale
  review dismissal, resolved threads, and strict `verify` and `CodeRabbit`
  checks. The existing administrator bypass remains unchanged; the approval
  job is optional.

The first consumer pilot was
[PR #92](https://github.com/acgetchell/dotfiles/pull/92), a GitHub Actions minor
update of `astral-sh/setup-uv` from 10.1.0 to 10.2.0:

| Evidence | Verified record |
|---|---|
| Head | `9c824763bf7472abb45fc3295bc066c67371451a`, authored by `dependabot[bot]`, committed by `web-flow`, with a verified signature |
| Approval | [Bot review](https://github.com/acgetchell/dotfiles/pull/92#pullrequestreview-5341429584) at 16:08:47 UTC on September 28; `commit_id` matches the head |
| Workflow | [Successful approval run](https://github.com/acgetchell/dotfiles/actions/runs/36448882262); `referenced_workflows` confirms shared SHA `0a02204d4a889dfc97f55286c008397ced05d6ad` |
| Merge gates | [PR CI](https://github.com/acgetchell/dotfiles/actions/runs/36448881588) passed at 16:17:38 UTC; `CodeRabbit` also succeeded |
| Auto-merge | `github-actions[bot]` enabled native `SQUASH` at 16:08:49 UTC and merged at 16:23:45 UTC, after required checks passed |
| Merge commit | [`e656bc4fbfd37e7c0b429b6a02923b9c627b47e3`](https://github.com/acgetchell/dotfiles/commit/e656bc4fbfd37e7c0b429b6a02923b9c627b47e3) |
| Default branch | [Dispatched CI](https://github.com/acgetchell/dotfiles/actions/runs/36516931876) passed on that exact merge SHA on September 29 UTC (September 28 Pacific) |

### Remaining hosted evidence

The September 28 [uv updater run](https://github.com/acgetchell/dotfiles/actions/runs/36449870462)
failed before creating a PR. While updating `nbformat`, Dependabot reported
`tool_version_not_supported`: the repository required uv `==0.12.19`, but the
hosted updater supported `0.12.18`. This is an updater/runtime mismatch; the
approval workflow was not reached. Request a fresh check from the repository's
Dependabot updates page once the hosted image supports the required version.
The failed dynamic run cannot be retried with `gh run rerun`.

Issue #85 remains open until a real dotfiles `uv` PR receives current-head bot
approval and native auto-merge, followed by CI on its actual merge commit.
Hosted evidence is also still needed for a preserving base merge, rejection of
a dependency-changing base merge or unexpected file, and dismissal of stale
approval after a changed head. PR #92 had a single commit and does not establish
those mutation cases. Keep generic regression tests in `research-repo-tools`;
the four local consumer tests cover the caller and repository policy only.

## Retired credential

The September 28 inventory confirmed that the deployed caller uses no personal
token, the repository Actions and Dependabot secret stores are empty, and no
repository environments exist. `CODERABBIT_REVIEW_TOKEN` is therefore already
absent from the applicable dotfiles stores. No credential deletion or revocation
was needed during this verification. Credentials belonging to other repositories
are outside this retirement; CodeRabbit remains a required status check.
