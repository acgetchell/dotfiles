# delaunay Tooling Review Notes

Use this reference when applying `project-tooling-review` to the `delaunay`
repository. Read `AGENTS.md`, `docs/dev/README.md`, and the routed owners under `docs/dev/` first;
repository guidance overrides stale details here.

The [tooling snapshot](delaunay-tooling-snapshot.json) records the reviewed
upstream revision for offline example checks. Refresh it from upstream paths
and live recipe definitions when changing these examples.

## Semgrep Surface

- `semgrep.yaml` is the source of truth for repository-owned rules.
- `tests/semgrep/` contains annotated positive and negative fixtures.
- The pinned `research-repo-tools` package owns fixture selection and execution;
  inspect its pin and configuration in `pyproject.toml` and the live
  `just semgrep-test` recipe. Keep the repository rule configuration authoritative.
- Preserve existing rule IDs when extending the same policy.
- The normal repository scan excludes deliberate fixture violations; use
  `just semgrep-test` to validate fixtures and `just semgrep` to check the real
  repository for false positives.
- Raw notebook JSON is suitable for narrow qualitative Semgrep patterns. Keep
  structural notebook validation in the shared tooling behind `just notebook-check`.
- In synthetic TeX fixtures, use the annotation form recognized by Semgrep test
  mode; `% ruleid` is not recognized by the current harness, while
  `// ruleid` is.

## Notebook And Asset Policy

- `just notebook-check` is lint-only and must not execute notebooks.
- Do not add an aggregate execute-all recipe or permanent runtime-based notebook
  directories. Execution cost is parameter-dependent.
- Ordinary notebook output belongs under `target/notebooks/`. Tracked figures
  are refreshed only through named recipes.
- Canonical validation figures live under `docs/assets/validation/` and are
  reused by documentation and papers; do not restore paper-local copies.

## Focused Validation

- Validate Semgrep configuration, then run `just semgrep-test` and
  `just semgrep`.
- Run `just check-config` after configuration changes and the focused Markdown
  validator when tooling guidance changes.
- Follow `docs/dev/commands.md` rather than defaulting configuration-only work
  to full `just ci`.
