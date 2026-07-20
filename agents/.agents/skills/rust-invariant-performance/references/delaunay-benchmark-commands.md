# Delaunay Benchmark Commands

Load this reference only for Delaunay benchmark execution, PR regression checks, release comparisons, or performance-document promotion. Confirm every command still exists in current repository guidance before running it.

## Routine and Focused Work

- Use the documented correctness gate before performance evidence; historically this has been `just ci` for broad core changes.
- Use `just perf-large-scale-smoke` as the broad construction-scale proxy when current guidance still defines it. Run it before and after the same change.
- Dimension-specific debug recipes may diagnose one case but do not replace the broad proxy for a broad claim.
- Use `just perf-no-regressions` for PR-ready local regression evidence when documented.

Treat small dimension-by-dimension movement as noise unless repeatable or material. A clear 3D or aggregate proxy regression should block a broad construction-performance claim.

## Release Evidence

When the repository still defines these roles:

- `just bench-latest`: curated release-signal Criterion suite
- `just bench-save-last`, `just bench-latest-vs-last`, `just bench-compare <baseline>`: saved-baseline reports
- `just performance-local`: isolated current-version versus published-release comparison
- `just performance-github-assets`: compare stored release benchmark assets
- `just performance-release`: promote a curated comparison into release documentation

Do not use release comparison or documentation-promotion commands as routine commit checks. Repository benchmark documentation and current recipes override names or roles here.
