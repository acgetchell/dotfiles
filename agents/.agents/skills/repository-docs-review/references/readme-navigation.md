# README Discovery and Published Navigation

- Keep README entry points easy to find: a copyable quickstart, brief capability
  descriptions, and direct links to fuller examples and contracts. Preserve useful
  detail in its canonical guide when shortening an overview; do not silently discard
  limitations or impose a fixed section layout or table size across repositories.
- Prefer the project's generated reference site for API documentation and worked
  API examples when that site supports them. Keep repository-owned development,
  operational, and scientific-background documents at their established repository
  or documentation-site destinations rather than duplicating the entire suite.
- When a README is also embedded in generated documentation or a package page,
  validate links and heading anchors in each actual rendering context. Relative
  repository paths can resolve against the wrong site base; use explicit URLs or
  the project's supported link transformation where needed.
- Check the intended version or revision of each destination and distinguish local
  rendering evidence from published availability. Route ecosystem-specific build,
  release, and API-link details to the relevant documentation specialist.
- Keep active README navigation independent of the package version: use the
  repository's default branch for current guides, source, and policies, and a
  stable alias such as docs.rs `latest` for published APIs. Check release updaters
  and their tests so the next release cannot restore version-dependent links.
  Verify destinations before tagging; rendering Markdown alone does not establish
  that linked pages exist. Retain immutable image and historical evidence links
  when their purpose requires provenance.

## Check GitHub navigation against the reviewed snapshot

For package README or navigation changes, prefer the repository's link checker
if it verifies both relative fragments and same-repository default-branch
fragments. Confirm coverage with a misspelled heading in a disposable copy
when the check's behavior is unclear.

With [Lychee](https://github.com/lycheeverse/lychee) available, run the
following from the root of the selected snapshot. Use the worktree for a
worktree review. For a staged or commit review, materialize the selected tree
first so the README and its destinations come from the same revision.
Replace `example/widgets` and `trunk` with the repository slug and its
configured default branch, escaping any regex metacharacters. A local
`git symbolic-ref --short refs/remotes/origin/HEAD` can identify that branch.

```sh
snapshot_uri=$(python -c 'from pathlib import Path; print(Path.cwd().as_uri())')
github_path='^https://github\.com/example/widgets/(?:blob|tree)/trunk/(.*)$'
lychee --offline --include-fragments=anchor-only --index-files 'README.md,.' \
  --remap "$github_path $snapshot_uri/"'$1' -- README.md
```

Pass additional in-scope Markdown files as arguments. For a template with a
non-Markdown extension, use its rendered `.md` path in the disposable snapshot
so relative paths and Markdown parsing match the packaged README. Lychee
resolves reference-style links and disambiguates repeated rendered headings
(for example, `#usage` and `#usage-1`). Fenced examples are skipped by default.
A broken fragment reports the referring file, destination, and remapped URL.

Keep tag and commit links tied to their named revisions. External sites and
other GitHub refs are excluded by offline mode. Record this check as evidence
for the selected snapshot and assess published availability separately when
the review calls for it.
