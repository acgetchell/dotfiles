# Whole-Repository Release Bootstrap

Use `baseline-release` for a whole-repository release-readiness review with a
POSIX `just ci` gate. It discovers repository instructions and routing candidates,
prepares schema-valid operator choices, and uses the normal bootstrap, preflight,
immutable dispatches, and bounded repair lifecycle. Use general bootstrap
`--input` for other commands, native Windows execution, or multiple validation units.

## Prepare And Bootstrap

Use the [Python environment](python-environment.md). From the reviewed checkout:

```sh
SKILLS_ROOT="$HOME/.agents/skills"
REVIEW_PROOF="$(mktemp -d "${TMPDIR:-/tmp}/release-review.XXXXXX")"
mkdir "$REVIEW_PROOF/validation"
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/capture_scope.py" \
  --repo "$PWD" --mode baseline > "$REVIEW_PROOF/capture.json"
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/review_graph_starter.py" \
  baseline-release --capture "$REVIEW_PROOF/capture.json" \
  --artifact-root "$REVIEW_PROOF/validation" --output "$REVIEW_PROOF/operator.json"
```

Read the returned discovery artifact. It lists root and applicable nested
`AGENTS.md` paths, classifier-selected routers, and the catalog projection, including
`unmatched_captured_paths` outside every consulted leaf's candidate patterns.
Root instructions become global; materialization discovers nested instructions
for each leaf's owned and declared dependency paths. Inspect these instructions
for transitive required files and declare them in global or leaf `instruction_paths`;
discovery does not infer references from prose. Restricted `--path` captures are rejected.
Discovery does not select semantic specialist dispositions or infer permission.

Edit `operator.json` with the authorized mode, actual environment/toolchain and
budget, applicable output policy, and executor prerequisites. The generated file
starts `review-only`, with blocked command policy and unconfirmed native tools.
Set `review-and-fix` when fixes are authorized. Supply semantic
`routing_overrides` for matched candidates and applicable contracts beyond path
matches, following [routing](planning-contract.md). All applicable leaves remain
required. Inspect `just ci` and nested recipes before allowing the exact command.

```sh
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/review_graph_bootstrap.py" \
  --capture "$REVIEW_PROOF/capture.json" --starter-config "$REVIEW_PROOF/operator.json" \
  --output "$REVIEW_PROOF/bootstrap.json"
```

Bootstrap derives release readiness, baseline scope, exact source and validation
identities, repository working directory, and recapture command. It runs read-only
preflight before returning a materialization command. Follow that command and its
scheduler continuation. Neither preparation nor bootstrap runs the gate or starts
workers. Preflight blockers remain saved; use the returned preflight retry command
for executor-only corrections. Planning changes require a new immutable output.

## Assess Captured Paths

Whole-repository baseline planning separately compares captured files with selected
or exactly reused leaf audit surfaces. Routers, validators, independent review,
synthesis, instruction reads and other context do not establish owned coverage.
The compact bootstrap receipt exposes `captured_path_inventory_reference`, its
digest and captured/unassigned/unassessed counts, even when dispatch is blocked.
Read that sidecar before fanout. It contains the complete
`unassigned_captured_paths`, `unassessed_captured_paths`, and recorded dispositions.
Candidate matches are discovery hints; the inventory uses actual semantic routing
decisions. Zero unresolved specialist candidates can still leave unassessed files.

For each unassessed path, either extend an applicable leaf's `review_surface` with
the material contract, or add a reasoned `captured_path_dispositions` entry to the
operator choices (or general planning input):

```json
[
  {
    "paths": ["config/release-policy.txt"],
    "disposition": "dependency",
    "reason": "Context for the selected tooling audit's release command contract",
    "catalog_ids": ["repo.tooling"]
  },
  {
    "paths": ["archive/retired-platform.txt"],
    "disposition": "archive",
    "reason": "Inspected as retained history; no current support promise or active references",
    "catalog_ids": []
  }
]
```

`dependency` requires selected or exactly reused audit catalog IDs; dispatch makes
these required context reads without claiming them as owned. Record actual reads and their unit
dependencies in the normal evidence. Verified inherited dependencies need not be
read again solely because of this declaration when only unrelated units need recheck.
Newly declared context without prior read evidence requires a fresh leaf review.
`historical` and `archive` require explicit classification; directory names alone
do not justify either. `user-excluded` requires an actual user scope exclusion,
retained as a report limitation. These three dispositions use empty `catalog_ids`.
Do not classify an active material contract as context or history to clear the gate.

Every path must be captured, unique across dispositions, and outside audit ownership.
Remove a disposition when adding that path to owned scope. Bootstrap blocks until
`unassessed_captured_paths` is empty; non-owned assessed paths remain visible in
`unassigned_captured_paths`. This checks accounting, not the truth of semantic
judgments or the completeness of instruction/dependency inspection. New source
states and changed routing require reassessment and a new immutable plan.

## Repository Effects And External Artifacts

| Operator field | Valid shape | Meaning |
| --- | --- | --- |
| `ignored_outputs` | `[{"path": ".pytest_cache", "kind": "cache"}]` | Repository-relative effects; planning verifies tracked ignore rules. |
| `external_artifacts` | `[{"path": "/tmp/review-proof/validation/python-cache", "kind": "cache"}]` | Absolute outputs within the existing `artifact_root`. |
| `artifact_root` | `"/tmp/review-proof/validation"` | External artifact boundary; execution stays in the checkout. |

The starter maps only `ignored_outputs` into repository-relative
`expected_workspace_effects`. Both groups become `allowed_artifacts` with their
appropriate repository status. Absolute paths in `ignored_outputs` fail with
the exact field and replacement shape. JSON paths are literal; shell variables
are not expanded. Roots cannot overlap the repository, including through symlinks.

The generated gate sets `UV_CACHE_DIR` to `artifact_root/uv-cache` and redirects
its log to `artifact_root/ci.log`; both are declared automatically. Examples for
other Python outputs depend on the inspected recipe:

- Repository `.venv` is a build output; `.pytest_cache` and concrete
  `package/__pycache__` directories are repository caches when actually created
  and ignored by tracked rules.
- If the recipe already uses `PYTHONPYCACHEPREFIX` or a pytest `cache_dir` outside
  the repository, declare those concrete paths in `external_artifacts`.
- Declarations do not redirect command outputs. Use general bootstrap `--input`
  when configuring additional command/environment overrides. Preserve existing
  pytest arguments and the exact command identity.

## Launch And Model Requirements

Materialization and scheduling receipts return `launch_manifest_reference` for a
digest-bound immutable JSON artifact; default stdout omits inline launch inventories.
Its `nodes` contain node ID, exact leaf skill and path, mode/result contract,
execution-view path/digest, and execution location, plus applicable executor,
timing, model, and validator compile requirements. Continuation paths are alongside
them. Read this manifest to launch scheduled nodes. Materialized nodes still need dependency-ready scheduling
before launch. Complete schemas and handoff catalogs stay behind the execution views.

For an explicitly requested model, pass `schedule-ready --worker-requirements`
with a JSON array using current node IDs, for example:

```json
[{"node_id": "audit-008", "model": "gpt-6-astra", "reason": "Maintainer requested Astra for this scientific judgment."}]
```

Set requirements before the first coordinator reservation. The scheduler retains
them in subsequent scheduling inputs and launch manifests, excludes those nodes
from the coordinator lane, and blocks exhausted creation fallback. The launcher
must honor the explicit model; scheduling does not attest to which model ran.
Repair graphs have new node IDs: supply their requirements before scheduling.

## Repair Continuation

During the initial broad audits, use [contract coverage units](coverage-partitioning.md)
where inspected dependencies establish independence. Whole-audit judgments and
uncertain dependencies remain conservative. A shared packet or historical report
does not authorize inherited coverage. Bounded source excerpts retain their existing
completeness flags; section indexing does not establish a semantic contract boundary.

`review-control begin-repair` exposes `validation_reconciliation` before editing.
Use `reconcile-validation-requirements` to expand late citations, package, security,
or experiment obligations on the current source state before repair replanning.
Carry the resulting obligations into the repair template. Source-only rebinding
does not rerun source judgments; changed execution contracts retain their existing
reassessment/recheck rules. Read the repair receipt's `coverage_continuation`, then
each replacement execution view before launching. Only bound `coverage_reuse`
permits affected-path inspection with inherited findings, validation and handoffs.

Completed rechecks can be origins for later affected verification: the compiler
replays their complete inheritance chain, keeps fresh reads distinct from inherited
paths, and conservatively groups the freshly reviewed surface. Original artifacts
and external runtime dependencies remain bound. Missing, changed or uncertain inputs
still require inspection; no sealed dependency partition is narrowed retroactively.

For a confirmed defect found during affected verification in an already repaired
file, use the [single verification follow-up](repair-validation.md#one-verification-follow-up)
inside the same batch. Expanded work or another follow-up uses the ordinary budget.

## Fixture And Accounting

```sh
just test-python agents/.agents/skills/review-graph/scripts/test_review_graph_baseline_release.py -q -s
```

The fixture prepares a real unrestricted baseline capture, performs bootstrap and
preflight, materializes the selected leaves, and completes their scripted initial
audit evidence. It batches scientific/tooling repairs, exercises external skill
and dispatch dependencies, tests instruction changes, and checks the first repair
and its bounded verification follow-up. Judgments are scripted protocol fixtures;
they do not establish review quality or mathematical validity.

Receipts measure preparation operations and serialized outputs, bootstrap operations
and capture/operator/generated-input bytes, plus launch-manifest and full dispatch
bytes. The documented path through materialization uses four CLI invocations:
capture, prepare, bootstrap (including preflight), and materialize. Count scheduling,
retries, actual review/model work, and command execution separately. Provider tokens
and cost remain unknown; serialized sizes and retained counts do not prove savings.
