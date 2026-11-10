---
name: changelog-commit-message
description: "Draft one changelog-ready commit message from the intended diff, following repository conventions and the user's message preferences."
---

# changelog-commit-message

Write commit messages from staged changes that respect the repository's own commit rules and produce useful `CHANGELOG.md` entries in the Keep a Changelog style.

Do not include test commands, validation results, or `Tests:` sections in the commit message unless the user explicitly asks for them. This preference overrides repository-local guidance that asks generated commit messages to include test results; validation belongs in PR descriptions, review notes, or the assistant's surrounding explanation, not in the changelog-oriented commit body.

The goal is not merely to summarize files. The message should describe the user-visible or maintainer-visible change in a way that changelog tooling can categorize, while remaining accurate to the staged diff.

## Workflow

### 1. Inspect only the intended changes

Start from staged changes:

- `git --no-pager status --short`
- `git --no-pager diff --cached --stat`
- `git --no-pager diff --cached --name-status`
- `git --no-pager diff --cached`

If there are no staged changes, say so and ask the user to stage files, unless they explicitly asked to draft from unstaged changes.

Do not stage files or run `git commit` unless the user explicitly asks.

### 2. Find repository-specific rules

Before drafting, look for local commit and changelog conventions. Prefer explicit repo rules over generic rules.

Check likely sources:

- `CONTRIBUTING.md`, `README.md`, `CHANGELOG.md`, `RELEASE.md`
- `cliff.toml`, `git-cliff.toml`, `release-plz.toml`, `cog.toml`
- `.gitmessage`, `.commitlintrc*`, `commitlint.config.*`
- `Cargo.toml`, `package.json`, `pyproject.toml`, `Makefile`, `justfile`
- recent history: `git --no-pager log -n 20 --format=%s`

Infer:

- required commit format
- allowed types and scopes
- whether changelog tooling consumes only the subject or also the body
- whether breaking changes require `!` and/or `BREAKING CHANGE:` footers
- whether maintenance-only commits are excluded from release notes

### 3. Default format when the repo has no stricter rule

Use Conventional Commits:

```text
type(scope): imperative summary

Optional body explaining why the change matters.

Optional footers.
```

Subject line rules:

- use imperative mood
- keep it concise, ideally 72 characters or less
- avoid trailing punctuation
- mention the changed behavior, not just changed files
- include a scope when it helps changelog grouping
- use `!` for breaking changes

Body rules:

- include a body when the staged diff has multiple meaningful changes, behavior changes, migration notes, or non-obvious rationale
- use short bullets for changelog-relevant details
- separate user-visible effects from internal mechanics
- avoid file-by-file narration unless the file boundary is the point
- do not include test commands, validation results, or a `Tests:` section; the changelog reader cares about behavior, not verification scaffolding

Footer rules:

- use `BREAKING CHANGE:` for semver-breaking behavior
- carry forward issue identifiers established by the task conversation, staged diff, or verified repository metadata; an issue number does not need to appear in changed files, and must never be invented
- when the staged commit fully resolves a known issue, automatically add a closing footer such as `Closes #123`; no separate request for the footer is needed. Assess completion against the issue requirements already available in context, reading the issue when that context is insufficient
- for partial or related work, use a non-closing reference such as `Refs #123` rather than claiming resolution
- keep issue-closing footers separate from pull-request references in the subject; one does not substitute for the other
- omit `Co-Authored-By` trailers by default, including when an agent runs `git commit`; add one only when the user explicitly requests it and provides or confirms the actual contributor's name and email
- never hard-code or infer a co-author identity from this skill, the tool being used, or the act of committing

### Release commits

When the intended commit prepares a release, default to this structure:

```text
chore(release): release $TAG

- Bump version to $TAG
- Update citation and package metadata
- Generate the release changelog
- Update release documentation
```

Replace `$TAG` with the release tag established by the conversation or staged
metadata, preserving the repository's tag style. Treat this as a flexible
starting point: adapt the wording, omit bullets that do not apply, and add
changelog-relevant details or comments supported by the staged diff.

When release preparation includes fixes or other substantive changes, check the
repository's changelog filters and template before choosing the subject. Use a
type and scope that include those changes in the generated changelog; when only
subjects are rendered, describe the substantive changes in the subject as well.
Keep a release-focused subject only when that configuration preserves their
visibility. If a required release convention conflicts with changelog visibility,
flag the conflict and request direction instead of assuming body details will
appear. Preserve required breaking-change markers and issue footers. Continue
to omit validation results unless the user requests them.

## Keep a Changelog mapping

Choose a type that maps cleanly to release-note categories in the current repository.

When no repo-specific mapping exists, use:

- `feat` for `Added`
- `fix` for `Fixed`
- `perf`, `refactor`, or `change` for `Changed`
- `deprecate` or `feat!` with a deprecation note for `Deprecated`
- `remove` or `feat!` / `refactor!` for `Removed`
- `security` or `fix` with a security scope for `Security`
- `docs`, `test`, `build`, `ci`, `chore`, or `style` only when the change is intentionally not user-facing or the repo maps those types into the changelog

The user's preferred workflow is one commit message covering the full staged diff, even when it spans multiple concerns or Keep a Changelog categories. Do not recommend splitting commits or return multiple messages unless the user explicitly asks. For non-release commits, choose the dominant semver-relevant type, preserve any breaking-change markers, and describe meaningful secondary changes in the body.

## Content guidance

Prefer messages that:

- are specific enough to become a useful changelog bullet
- name the public API, command, feature, crate, package, or workflow affected
- mention behavior changes and compatibility implications
- call out migration or configuration changes
- avoid implementation-only phrasing when user-visible behavior changed

Avoid:

- vague subjects such as `update files`, `fix stuff`, `misc cleanup`, or `changes`
- summaries based only on filenames
- claiming a bug fix, feature, or breaking change not supported by the staged diff
- including unstaged work
- leaking secrets or local machine-specific values from diffs
- describing tests added to validate the change in feat/fix/perf/refactor/etc. commits; treat new tests as expected verification scaffolding rather than changelog content
- adding validation summaries because a repository template asks for them, unless the user explicitly requests that text

Exception: describe tests when they are the change, either in a test-only commit or as an independent coverage improvement within a mixed commit. Continue omitting tests that merely verify another change already described in the message.

## Output format

Return one recommended commit message first, in a plain text code block so the user can copy it.

Then include a short rationale only if useful:

- detected repo convention
- chosen type/scope
- changelog category it should produce

If the user asks for only the message, output only the commit message.
