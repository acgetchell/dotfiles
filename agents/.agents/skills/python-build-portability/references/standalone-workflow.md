# Standalone Python Build Portability Workflow

Read this reference only when `python-build-portability` is invoked directly
without an exact parent scope, validation ledger, and result contract.
Review-graph and Python-orchestrator dispatches already own this information.

## Scope Modes

Use changed-code mode by default. Use whole-repository mode only for an
explicit baseline or release-readiness audit.

## Focused Validation

Prefer repository recipes. Otherwise select from:

- `uv lock --check`
- `uv run --locked ruff check .`
- `uv run --locked ruff format --check .`
- `uv run --locked ty check`
- `uv build`
- artifact inspection followed by an isolated uv wheel install
- external import, entry-point, extra, and package-resource smoke tests
- a targeted supported-Python or platform configuration through uv

Do not upgrade dependencies or rewrite the lockfile unless requested. Request
approval when uv needs unavailable network access or cache writes outside the
sandbox.

## Standalone Report

Lead with build or portability blockers. For each finding, identify the
affected artifact or configuration, declared contract, and smallest correction.
End with uv, Ruff, and ty commands; artifacts and configurations validated;
external-consumer evidence; remaining matrix gaps; and tooling or test-quality
handoffs.
