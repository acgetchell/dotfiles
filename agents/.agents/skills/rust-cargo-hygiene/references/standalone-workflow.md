# Standalone Cargo Hygiene Workflow

Read this reference only when `rust-cargo-hygiene` is invoked directly without
an exact parent scope and result contract. Review-graph and Rust-orchestrator
dispatches already own scope and reporting.

## Scope Modes

In default mode, audit newly added or modified manifests, toolchain files, lint
configuration, and crate-root attributes. Ignore unrelated unchanged
configuration unless it affects the changed manifest surface.

Use whole-repository baseline mode only when explicitly requested. Cover all
workspace manifests, committed lockfile policy, toolchain and Cargo config,
lint configuration, docs.rs metadata, and crate-root lint attributes.
Prioritize release risk, semver impact, MSRV drift, feature breakage, unsafe or
lint enforcement, and dependency correctness. Separate release blockers from
historical cleanup.

## Standalone Report

Classify the result as `PASS`, `NEEDS IMPROVEMENT`, or `FAIL`. Report:

- manifest, feature, MSRV, lint, and workspace findings with locations
- required metadata, dependency, feature, toolchain, lint, workspace, and
  publishing corrections
- optional future-facing metadata, documentation, and feature improvements
