# Scientific Correctness Fix Workflow

Read this reference only when fixes are explicitly authorized. Review-only
workers do not need it.

- Repair the lowest layer that owns the violated invariant.
- Preserve typed scientific failures and diagnostic context.
- Keep exact paths exact and make approximation or rounding opt-in when the
  contract requires it.
- Add a deterministic regression test and an independent oracle or property for
  the corrected behavior.
- Update public claims, examples, fixtures, and benchmark coverage when their
  scientific meaning changes.
- Follow repository semver policy; do not preserve a compatibility alias that
  keeps a scientifically incorrect model alive.
- Rerun the scientific audit if later refactoring changes formulas, arithmetic
  order, tolerances, precision or fallback behavior, RNG semantics, or
  scientific fixtures.
