# Cargo Release Readiness

Read this reference only for explicit release preparation, version-bump, or
publish-readiness work. Ordinary manifest, feature, and hygiene reviews do not
load it.

## Version Changes

Do not automatically bump package or lockfile versions, README dependency
snippets, or related references during ordinary Cargo hygiene, feature, fix, or
review work. Version bumps are maintainer-driven release steps. Recommend or
perform them only when the user explicitly requests release or version-bump
work or is following the repository release procedure.

Report semver implications of changed code as findings or release notes even
when the actual version remains unchanged.

## Release Checklist

Check that:

- `CHANGELOG.md` matches the manifest version
- documentation is updated before publishing because crates.io cannot
  republish documentation without a version bump
- version references are consistent within the explicit release workflow
- `cargo publish --dry-run` would succeed with the current manifest
- yanked or deprecated dependencies are absent
- declared MSRV and supported feature and target evidence is available from
  `rust-build-portability`

`project-tooling-review` owns the commands, workflows, and runners that produce
release evidence.
