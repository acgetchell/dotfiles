# delaunay Tooling Review Notes

Use this reference when applying `project-tooling-review` to the `delaunay`
repository. Read `AGENTS.md` and the routed owners under `docs/dev/` first;
repository guidance overrides stale details here.

## Semgrep Surface

- `semgrep.yaml` is the source of truth for repository-owned rules.
- `tests/semgrep/` contains annotated positive and negative fixtures.
- `scripts/semgrep_fixture_config.py` selects annotated rules from the shared
  configuration for each fixture. Keep the shared config authoritative.
- Preserve existing rule IDs when extending the same policy.
- The normal repository scan excludes deliberate fixture violations; use
  `just semgrep-test` to validate fixtures and `just semgrep` to check the real
  repository for false positives.
- Raw notebook JSON is suitable for narrow qualitative Semgrep patterns. Keep
  structural notebook validation in `scripts/notebook_check.py`.
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
- Run `just lint-config` after configuration changes and the focused Markdown
  validator when tooling guidance changes.
- Follow `docs/dev/commands.md` rather than defaulting configuration-only work
  to full `just ci`.
