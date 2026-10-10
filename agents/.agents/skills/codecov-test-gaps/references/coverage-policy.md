# Coverage Policy

## Audit `codecov.yml` itself

`codecov.yml` (or `.codecov.yml`) defines what "good coverage" means for the project. Read it before reviewing the report so findings align with the policy that is actually enforced.

Check:

- `coverage.status.project` and `coverage.status.patch` thresholds, including `target`, `threshold`, and `informational`
- `coverage.range` (the color band shown in the UI)
- `flags` and per-flag carryforward, used for matrix builds (OS variants, feature combinations)
- `component_management` definitions when subsystems have different policies
- `ignore:` blocks that exclude paths from coverage entirely
- `comment` configuration so the PR comment exposes the right information

Flag:

- thresholds set so loose that regressions never fail the check
- `ignore:` entries that hide code which should be tested
- carryforward that masks broken matrix legs
- thresholds in `codecov.yml` that disagree with the project's stated policy

When the right answer is to update `codecov.yml` rather than write a low-value test, propose the YAML change explicitly.
