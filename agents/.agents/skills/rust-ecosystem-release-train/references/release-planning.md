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
for each check before declaring that release complete.

Prefer repository files and native GitHub metadata over issue-body prose. Use
official Rust release sources for schedules and final release notes.

## Build The Release Plan

Apply the [shared planning contract](../../issue-planning-to-release/SKILL.md)
to each participating release, then add its Rust/MSRV and Cargo requirements.
Include a Rust-adoption issue only when the selected train's policy includes that
work. Repository release guides own the executable commands.

For a requested end-to-end train, a separate ecosystem capstone may require all
published crates to resolve and final downstream validation to pass. Its broader
completion criterion must not become a downstream-adoption blocker on any
upstream publication capstone. Plan shared Python tooling publication and later
crate-repository adoption through the same ownership boundary.

When the selected train's policy includes stable-Rust adoption, finish compatible
feature and defect work, audit beta compatibility, and prepare release candidates
before stable ships. Do not close that adoption gate until the final release
notes and stable toolchain have been checked.

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
