---
name: changelog-commit-message
description: "Write repository-aware commit messages from staged changes that parse into useful Keep a Changelog entries. USE FOR: generating a commit message, writing a changelog-friendly commit, summarizing staged changes, Conventional Commits, git-cliff/release-plz/cocogitto-compatible messages, semver-sensitive commit messages, deciding commit type/scope/body/footer from staged diffs. DO NOT USE FOR: making code changes, staging files, committing unless explicitly asked, generic prose summaries, PR descriptions, or repositories without staged changes unless the user explicitly asks to draft from unstaged changes."
---

# changelog-commit-message

Write commit messages from staged changes that respect the repository's own commit rules and produce useful `CHANGELOG.md` entries in the Keep a Changelog style.

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
- do not narrate the tests used to validate the change; the changelog reader cares about behavior, not verification scaffolding

Footer rules:

- use `BREAKING CHANGE:` for semver-breaking behavior
- include issue references only when visible in the staged changes or requested by the user
- include `Co-Authored-By: Oz <oz-agent@warp.dev>` when the agent is actually committing or the current workflow requires attribution

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

If staged changes mix unrelated Keep a Changelog categories, recommend splitting the commit. If the user still wants one commit, choose the dominant semver-relevant type and describe secondary changes in the body.

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

Exception: when the commit is genuinely test-only (e.g., `test:` type or a tests-only scope), the message should describe the new tests because the tests are the change.

## Output format

Return the recommended commit message first, in a plain text code block so the user can copy it.

Then include a short rationale only if useful:

- detected repo convention
- chosen type/scope
- changelog category it should produce
- any split-commit recommendation

If the user asks for only the message, output only the commit message.
