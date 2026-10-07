# Branch Bootstrap Starter

Use `review_graph_bootstrap.py --starter-config` for a branch review whose
repository gate is `just ci` on a POSIX executor. It expands the
[operator choices](bootstrap-starter-v1.json) into the complete public
[planning input](schemas/planning-input-v1.schema.json), plans the graph, and
runs read-only validation preflight in one invocation. Use general `--input`
for other commands, scopes, execution isolation, or multiple validation units.

## Run It

Use the [Python environment](python-environment.md). From the reviewed repository,
choose an external proof directory and copy the example there:

```sh
SKILLS_ROOT="$HOME/.agents/skills"
REVIEW_PROOF="$(mktemp -d "${TMPDIR:-/tmp}/review-proof.XXXXXX")"
mkdir "$REVIEW_PROOF/validation"
cp "$SKILLS_ROOT/review-graph/references/bootstrap-starter-v1.json" \
  "$REVIEW_PROOF/operator.json"
```

Edit `operator.json` before bootstrap:

- Set `artifact_root` to the absolute path of the existing `validation` directory.
  JSON paths are literal; `$HOME`, shell variables, and `~` are not expanded.
- Record the authorized review mode, consulted routers, applicable instruction
  paths, execution profile, environment, toolchain, platform, features, and budget.
  Add sparse `routing_overrides` only when semantic routing needs them.
- List concrete repository-relative `ignored_outputs` with their artifact kinds.
  The example's Python directories are illustrative; inspect the recipe's actual
  outputs, including nested caches and source-adjacent intermediates. Planning
  verifies each against tracked repository ignore rules.
- Inspect `just ci`, its nested recipes, and test fixtures against the task's
  restrictions. Set `command_policy.disposition` to `allowed` only when that
  exact gate is authorized, and record why. This preset permits declared outputs
  but no source or Git mutation. A fixture that mutates Git can still violate
  a task-wide restriction even if it uses a temporary repository.
- Adapt host `executables`, optional `uv_projects`, and `native_available` to
  the observed executor. The example starts blocked and native availability is
  unconfirmed. See [preflight](validation-preflight.md) for uv environment paths.

Capture with the requested branch base, then bootstrap; neither command mutates
Git, runs `just ci`, installs tools, or starts workers:

```sh
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/capture_scope.py" \
  --repo "$PWD" --mode branch --base origin/main > "$REVIEW_PROOF/capture.json"
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/review_graph_bootstrap.py" \
  --capture "$REVIEW_PROOF/capture.json" \
  --starter-config "$REVIEW_PROOF/operator.json" \
  --output "$REVIEW_PROOF/bootstrap.json"
```

The starter derives scope and validation fingerprints, captured paths, the
recapture command, repository working directory, and concrete change target
from the capture. The planner still owns routing, independent review, and node
identities. It supplies `baseline: true` and `requested_scope: branch`; baseline
identifies the repository gate without broadening review scope.

The generated command sets `UV_CACHE_DIR` to `artifact_root/uv-cache` and redirects
stdout/stderr to `artifact_root/ci.log`, with shell-quoted paths and the original
`just ci` exit status. Confirm nested recipes honor the cache override. The gate
executes later under the existing validator protocol.

## Artifact Root Versus Execution Isolation

| Choice | Meaning |
| --- | --- |
| `isolation_root: <external directory>` | Bounds permitted external artifacts, including cache and log paths. |
| `requires_isolation: false` | Validation keeps the captured repository as its working directory; declared repository effects must be ignored. |
| `requires_isolation: true` | Validation working directories must also be absolute and under the external isolation root. Arrange the isolated source separately using general `--input`. |

The starter uses the first two rows together. An external artifact requires an
isolation root even when execution stays in the checkout. Setting the boolean
to true is not the remedy for a missing artifact root. Roots must not overlap
the repository, including through symlinks. An existing external proof directory
or a dedicated child is suitable; the starter does not copy or relocate source.

## Preflight And Handoff

Bootstrap validates the generated planning input, constructs the plan, binds
preflight policy to its exact command and node ID, and runs the existing
`preflight-validation` checks before returning `next_command`. The bundle contains
`planning_input`, `preflight_input`, `preflight_report`, and the normal immutable
materialization/lifecycle inputs. No hand-authored plan or capture placeholders
are needed.

An invalid schema or artifact contract fails before saving a bundle. A routing
or execution blocker saves the bundle for inspection, returns exit code 2,
sets receipt `dispatch_allowed: false`, and leaves `next_command` null. Resolve
operator choices and bootstrap to a new output path; existing bundles cannot be
overwritten with different contents. Full output retains the planner's own
`plan.dispatch_allowed`; executor readiness is recorded separately in
`preflight_report`. For deliberate partial progress with blocked validation,
follow the existing [preflight hold workflow](validation-preflight.md).

On success, follow the receipt's `next_command` to materialize the unchanged
dispatch contracts. Preflight is a prerequisite observation, not validation
evidence or proof of sandbox write access. Rerun it if the executor changes:

```sh
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/review_graph_runtime.py" \
  preflight-validation --input "$REVIEW_PROOF/bootstrap.json" \
  --output "$REVIEW_PROOF/preflight-recheck.json"
```

Continuation operations retain their existing immutable dispatch/journal
bindings and [continuation inputs](state-transitions.md).

## Deterministic Fixture And Accounting

From dotfiles, run the focused fixture with metrics visible:

```sh
UV_CACHE_DIR=.uv-cache uv run --locked pytest \
  agents/.agents/skills/review-graph/scripts/test_review_graph_starter.py \
  -k test_starter_bootstrap_fixture -q -s
```

The fixture reads an existing committed source fixture and tracked ignore policy
using the repository's full history. It performs no Git mutation or real CI run.
It exercises bootstrap, public schemas, preflight replay, and immutable retries;
the companion command test uses a temporary stand-in to verify quoting and a
failing exit status. Routing and proof checks remain enabled.

Each starter receipt measures actual capture/operator file bytes and compact,
sorted JSON bytes for the generated planning/preflight inputs. Its operation
count covers that invocation: bootstrap and embedded preflight (two operations,
one CLI invocation). The documented initial path adds capture, totaling two CLI
invocations and three protocol operations. Fixture retries and explicit preflight
rechecks are additional operations, excluded from that initial-path count.
Sizes depend on paths, capture size, and routing; generated bytes are not model
tokens. `model_tokens` and `provider_cost` remain null when unavailable. These
measurements establish protocol construction only, not review quality or
wall-clock savings.

A local POSIX CLI replay of this fixture measured 1,038 operator-input bytes,
56,526 capture-input bytes, 4,223 generated planning-input bytes, and 27,223
generated preflight-input bytes. Bootstrap and embedded preflight completed in
one CLI invocation; a separate invocation materialized five dispatches without
starting workers. These are observed serialized sizes for that fixture and path
layout, not a comparison of model cost or review performance.
