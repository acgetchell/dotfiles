# Validation adoption evidence

This records the command graph, validator ownership and measured results for
[the v0.2.7 integration issue](https://github.com/acgetchell/dotfiles/issues/263)
and [PR #265](https://github.com/acgetchell/dotfiles/pull/265). The command owners
remain the [Justfile](../justfile), [CI workflow](../.github/workflows/ci.yml),
and [Linux launcher](../scripts/linux_review.py). The shared package is the
published `research-repo-tools==0.2.7`; no managed Cargo tools are declared here,
so shared Cargo compilation caching is not applicable.

## Command and dependency graph

The local graph below is in execution order. Indentation denotes dependencies;
the two children of `_check-execution` run concurrently. Just coalesces the
`test-review-contracts` dependency, so it runs once before either execution lane.

```text
ci -> check
  python-sync -> _ensure-uv
  test-review-contracts -> _ensure-uv
  _check-policy (serial)
    shell-check
    git-config-check
    justfile-fmt-check -> _ensure-just
    toml-check -> _ensure-uv
    yaml-check
      yaml-fmt-check -> _ensure-dprint, _ensure-uv
      yaml-lint -> _ensure-uv
    markdown-check -> _ensure-rumdl, _ensure-uv
    github-actions-check
      action-lint -> _ensure-actionlint
      workflow-allowlist-check -> _ensure-uv
      zizmor -> _ensure-uv
    check-skills -> _ensure-uv
    python-check -> _ensure-uv
  _check-execution (parallel)
    _check-semgrep (serial)
      semgrep -> _ensure-uv, _ensure-semgrep
      semgrep-test -> _ensure-uv, _ensure-semgrep
    test-python -> test-review-contracts
```

`python-sync` owns environment mutation before validation. `_ensure-*` checks
verify executable availability/version; `_ensure-semgrep` also checks the root
locked environment without syncing it. Scan and fixture operations share that
environment and remain serialized. Pytest owns isolated temporary outputs and
uses four workers by default. `just --jobs 1 ci` serializes the two recipe lanes;
`DOTFILES_TEST_WORKERS=0 just --jobs 1 ci` also serializes pytest. Neither fallback
changes the selected validator/test inventory.

Hosted command dependencies are:

```text
verify (macOS)
  checkout/full history -> Python/Just/dprint/rumdl/uv -> python-sync
  Stow -> tools-sync -> security -> ci
security -> security-osv, security-secrets
Linux portable review (Ubuntu 24.04)
  checkout -> host prerequisites -> linux setup -> repeated linux setup
  resource report -> linux check -> linux smoke -> evidence upload
linux setup -> locked environment/tool checks -> yaml-fmt-check/plugin warmup
linux check -> environment/skill checks -> timed ci (offline, no sync)
linux smoke -> environment/skill checks -> timed graph publication/final proof
Validation timing (Linux and Windows)
  checkout -> native shells/Python/Just/uv -> test-validation-timing
  Windows only -> root locked Semgrep engine smoke
GitHub Actions Security Analysis (separate zizmor workflow)
  checkout -> uv -> zizmor-check --require-online findings gate
  -> SARIF generation -> permitted SARIF upload
```

The jobs retain their existing names and native coverage. No required validator
was removed or assigned to a different job. macOS and Linux run complete local
CI; Windows retains its native executor/timing and scanner checks. An offline
audit is not evidence of the separate authenticated online audit.

## Validator owners

In this table, CI means local `just ci`, hosted macOS `verify`, and Linux's
offline `ci` invocation. Shared commands own generic mechanics; dotfiles owns
the selected source inventory, policy and consumer assertions.

| Validator | Final implementation owner | Execution owner |
| --- | --- | --- |
| Shell syntax | `shell-check`, Bash over the six declared launcher/bootstrap scripts | CI policy lane |
| Git configuration syntax | `git-config-check`, Git parsing `git/.gitconfig` | CI policy lane |
| Just formatting | `justfile-fmt-check`, pinned Just | CI policy lane |
| TOML parsing | `toml-check`, shared file inventory and `tomllib` | CI policy lane |
| YAML/CFF formatting and lint | `yaml-fmt-check` / dprint and `yaml-lint` / yamllint | CI policy lane; Linux setup also warms the formatter plugin |
| Markdown | `markdown-check`, shared inventory and rumdl | CI policy lane |
| Actions syntax | `action-lint`, shared inventory and actionlint | CI policy lane |
| External Actions allowlist | `workflow-allowlist-check`, shared Actions checker with committed policy | CI policy lane |
| Offline workflow security | `zizmor`, shared scanner with explicit offline mode | CI policy lane |
| Skill metadata/references | `check-skills`, `scripts/skill_validate.py` | CI policy lane |
| Python baseline, formatting, lint and types | `python-check`, shared pipeline with complete repository Ruff/Ty policy | CI policy lane |
| Prompt/routing contracts | `test-review-contracts`, dedicated pytest module | CI early serial gate |
| Source policy scan | `semgrep`, root locked engine and `semgrep.yaml` | CI scanner lane |
| Policy fixtures | `semgrep-test`, shared fixture harness and repository expectations | CI scanner lane, after source scan |
| Remaining Python, shell, Stow and review-graph regressions | `test-python`, complete remaining pytest inventory | CI pytest lane, after early contracts |
| Dependency advisories | `security-osv`, shared OSV checker over `uv.lock` | macOS `verify` and explicit local `security` |
| Secrets | `security-secrets`, shared Gitleaks history/current-files scan | macOS `verify` and explicit local `security` |
| Online workflow security and SARIF | `zizmor-check`, shared scanner | `GitHub Actions Security Analysis`; findings gate remains distinct from report production |
| Linux installation, repeatability and installed environment | `bin/linux-review.sh`, `scripts/linux_review.py` | `Linux portable review`, before offline checks |
| Native executor shells/timing | `test-validation-timing`, `review-validator/scripts/test_run_timed.py` | Linux and Windows timing jobs; also covered by the platform-applicable CI tests |
| Native Windows scanner | `scripts/semgrep_smoke.py`, root dev lock | Windows timing job; requires one expected finding and no scanner errors |
| Graph publication/final proof | `review-graph/scripts/review_graph_smoke.py` | Linux smoke after offline CI; `review-environment-smoke` is the local entry point |

Focused aliases preserve these owners: `markdown-lint` delegates to
`markdown-check`; `python-lint` delegates to `python-check`; `python-ci` composes
Python checks/tests. `python-baseline-check`, `python-typecheck`,
`python-fixture-lint` and `skill-check` expose subsets already covered by CI.
`security-check` aliases `security`. `tools-check` is the explicit installed-tool
verification surface; provisioning verifies the installed selections as well.

Additional opt-in checks retain separate ownership: `release-dependency-builds`
prepares authenticated native Python builds after `python-sync`, then
`release-dependencies` verifies registry provenance. `brew-check`, `stow-check`
and `stow-verify` inspect the selected workstation; their implementation fixtures
run in CI without requiring changes to the user's home. `typesafe-check` /
`linux-probe`, CodeRabbit reviews, Rust review fixtures, routing experiments and
workflow/Python benchmarks remain explicitly requested evaluations rather than
new CI gates. Formatter/update/setup commands are mutation surfaces, not extra
validators silently omitted from CI.

## Native CI measurements

Both runs below completed successfully, attempt 1, on 9 November 2026 Pacific
time. Run A is [42722884874](https://github.com/acgetchell/dotfiles/actions/runs/42722884874)
at `811946a9450393b647fff497c2e37d3ade940043`; run B is
[42735037741](https://github.com/acgetchell/dotfiles/actions/runs/42735037741)
at `aad62da8c64c1d2ff5b619f92ae33175640f264b`. Only seven Markdown files changed
between these revisions: workflow, recipe, lock, source and executable-test
inputs are identical. Documentation inputs differ, so these are representative
equivalent-coverage observations, not a controlled speedup experiment.

Seconds below come from GitHub job/step timestamps. Queue time is job creation
to runner start; execution is runner start to job completion, including setup
and cleanup. Runner usage sums those execution intervals, without billing
multipliers or minute rounding. It is not summed CPU time. Workflow elapsed is
run creation to the last CI job completion; parallel job times do not add to it.

| Native job | A queue / execution (s) | B queue / execution (s) |
| --- | --- | --- |
| macOS `verify` | 2 / 609 | 5 / 612 |
| Ubuntu `Linux portable review` | 2 / 365 | 2 / 373 |
| `Validation timing (Linux)` | 3 / 20 | 2 / 28 |
| `Validation timing (Windows)` | 2 / 60 | 1 / 53 |
| Sum of job queue / runner usage | 9 / 1,054 | 10 / 1,066 |
| Workflow elapsed, including scheduling | 612 | 618 |

The totals cover the four jobs in the CI workflow; the separate online zizmor
workflow is excluded. Both online workflow audits also passed. Stage detail:

| Stage | A (s) | B (s) |
| --- | --- | --- |
| macOS Python installation | 41 | 42 |
| macOS root dependency sync | 13 | 2 |
| macOS managed security scanner installation | 4 | 4 |
| macOS dependency/secret audit | 7 | 7 |
| macOS complete `just ci` | 522 | 532 |
| Linux fresh unprivileged setup | 19 | 20 |
| Linux repeated setup, same command and verification | 1 | 1 |
| Linux complete offline suite | 323 | 327 |
| Linux graph publication/final-proof smoke | <1 | <1 |
| Linux timing tests | 2 | 4 |
| Windows timing tests | 7 | 6 |
| Windows root Semgrep engine smoke | 25 | 23 |

Subsecond step timestamps round to the same second; `<1` indicates that API
precision, not zero execution. Each macOS run passed 24 early contract tests
plus 2,760 remaining tests, with two platform skips. Each Linux suite passed
24 early contracts plus 2,810 remaining tests, with one Windows-only skip.
Windows timing and scanner checks passed in both runs. Native workloads differ
by platform and are not substituted for one another.

## Cache conditions and local comparison

The macOS dependency cache was **cold in A**: setup-uv logged no cache for its
exact key. It was **warm in B**, which restored that same key:

```text
setup-uv-2-aarch64-apple-darwin-macos-16-3.15.2-pruned-78eff38915efc03fcb0a159a8225b6bd81c508790e502d7d90da2e7498628b47
```

Both runs created fresh virtual environments. Just, dprint and rumdl binary
caches hit in both; Python 3.15.2 was absent from the runner tool cache in both.
Thus cold/warm refers specifically to the uv dependency cache, not every cache
on the runner. Sync took 13/2 seconds, full CI 522/532 seconds, and the macOS
job 609/612 seconds. These observations do not demonstrate an overall speedup.

Linux uses fresh job-private installation/cache directories without Actions
cache restoration. Its first and repeated setup commands verify the same pinned
tool/environment contract and measured cold/warm setup at 19/1 and 20/1 seconds.
The later offline suite runs against that provisioned environment. Windows
timing jobs disable setup-uv caching; no warm-cache Windows full-suite result
is claimed. There is no managed Cargo cache to measure in dotfiles.

On one warm macOS worktree, the complete local serial-recipe and parallel-recipe
runs took 579.29 and 556.10 seconds. Both retained four pytest workers and the
same validator/test inventory. The fully serial pytest fallback is documented
but is not part of that timing pair. Native and local results agree that pytest
dominates elapsed time; a single observation per schedule on shared runners
does not establish a general performance improvement.

This report documents observed commits. Later code, policy or workflow changes
still require their applicable checks and current native merge gates; these
measurements do not pre-certify an uncommitted follow-up.
