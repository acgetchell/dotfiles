# Release Planning and Publication

## Capture Current State

For every repository in the graph, inspect:

- package version, `rust-version`, public dependency requirements, and lockfile;
- `rust-toolchain.toml`, `clippy.toml`, active MSRV documentation, and target matrix;
- latest GitHub and crates.io releases;
- open milestones, release issues, native dependency edges, and open PRs;
- `justfile`, workflow files, Dependabot configuration, and action/tool pins;
- `pyproject.toml`, `.python-version` when present, `uv.lock`, dependency groups,
  overrides, and support-package behavior; route any discovered repository edits on
  these Python surfaces through `python-review-orchestrator` in orchestrated mode
  and include `python-production-review` synthesis in the evidence chain before
  declaring release readiness.
- Python support-package versions, release/citation metadata, generated changelog
  fragments, and documentation version snippets, validating against the shared
  invariants in [`references/repositories.md`](repositories.md)
- `semgrep.yaml`, repository-owned rules, fixtures, fixture validators, and
  Semgrep CI integration.

After any release publication, perform post-publication package inspection and
documentation/release verification for affected repositories with explicit evidence
for each check before declaring a crate release-ready.

Prefer repository files and native GitHub metadata over issue-body prose. Use
official Rust release sources for schedules and final release notes.

## Build The Release Plan

1. Identify or propose one Rust-adoption issue and one release-capstone issue
   for each participating release; create them only after authorization.
2. Treat a release milestone as a publication contract. Review every open item;
   keep genuine release gates and move unrelated work rather than silently
   delaying the train.
3. Make each release capstone blocked by all retained local gates and by the
   release capstone of each upstream crate it consumes.
4. Make downstream integration work depend on the upstream **published-release
   capstone**, not merely on the implementation issue that introduced an API.
5. Work bottom-up. Before each publication, explicit authorization is required for
   any mutation, including moving work items, adding dependency links, publishing
   or closing issues, and updating any downstream Cargo or lockfile state. When
   missing, emit reviewable proposals instead of applying direct changes.
6. Work bottom-up. After each publication, update downstream Cargo
   requirements/locks through the registry, then run downstream contract
   validation; only execute those updates with explicit authorization.
7. Keep the final ecosystem capstone open until the published crates resolve
   without overrides and the complete downstream validation passes.

Before stable ships, finish compatible feature and defect work, audit beta
compatibility, and prepare release candidates. Do not close the stable-Rust
adoption gate until the final release notes and stable toolchain have been
checked.

## Coordinate Focused Skills

- Use `github-issue-planning` for native blockers, milestones, labels, and
  release-capstone metadata.
- Use `project-tooling-review` when implementing or auditing Just, CI, pins,
  Semgrep, uv, or repository-rule changes.
- Use `python-review-orchestrator` in orchestrated mode for dependency,
  packaging, release-surface, or lockfile work touching `pyproject.toml`, `uv.lock`,
  support-package behavior, or other Python-owned surfaces; require an accepted
  `python-production-review` synthesis pass before finalizing those release-ready
  decisions.
