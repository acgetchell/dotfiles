# Shared Tooling Alignment

## Align Shared Tooling

Treat tooling alignment as semantic synchronization, not textual sameness.
Propagate a shared improvement when the same contract applies; retain a
repository-specific difference when its workload or scientific role requires
it, and record the rationale.

For each release train, compare and intentionally reconcile:

- canonical Just recipe names, composition, and operator-facing behavior;
- GitHub workflow purposes, triggers, permissions, matrices, artifact handling,
  and immutable action pins;
- repository-owned tool pins and Dependabot coverage;
- Cargo dependency versions, feature choices, locks, MSRV, and release profiles;
- Python baseline, support-package metadata, uv dependency groups, exact tool
  pins, security overrides, and locks;
- Semgrep rule coverage, include/exclude surfaces, fixture conventions,
  diagnostics, SARIF upload, and validation commands.

Never bulk-copy configuration without checking the receiving repository's
commands, features, platforms, artifacts, and failure contracts. Validate the
shared contract locally and in the repository that owns each change.
