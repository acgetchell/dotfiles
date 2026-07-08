# delaunay Routing Notes

Use this reference when `rust-review-orchestrator` is running in the `delaunay`
crate or closely related computational-geometry code.

## Repository Guidance

- Read local repository instructions before editing, especially `AGENTS.md` and
  `docs/dev/commands.md` when present.
- Prefer the repository's `just` recipes from `docs/dev/commands.md` over generic
  Cargo fallbacks.
- Use `just rust-core-check` while iterating on Rust library source that affects
  core behavior.
- Escalate to `just ci` when public API and core invariant behavior changed
  together, when mutation/topology/numerical behavior changed broadly, or when
  repository guidance requires it.

## Review Emphasis

- Preserve the validation hierarchy: local validity, combinatorial consistency,
  intrinsic topology, embedding validity, and geometric predicates are separate
  responsibilities.
- Keep intrinsic simplex dimension distinct from ambient embedding dimension.
- Treat robust predicate sign behavior, exact fallbacks, deterministic
  degeneracy handling, adjacency, manifold, Euler characteristic, and topology
  guarantees as correctness constraints.
- Prefer fixes that preserve typed errors and layer-specific diagnostics over
  fast boolean shortcuts.

