# Bounded Repair And Delivery Lifecycle

Use one comprehensive initial review. Batch all authorized findings, including
optional findings when requested, then verify affected contracts and reuse
independently proved unchanged evidence. Scientific checks, initial exhaustive
coverage, immutable evidence, and exact-commit native CI retain their existing
requirements.

## Shared Run Authority

Initialize new plans with the repository root through `plan_from_document` or
`plan_graph`. The runtime issues immutable `review_lifecycle.run_control`
identity and generation references before producing plan copies. Bootstrap uses
an external control store beside its output; its identical retries retain those
references. Low-level initialization can supply an external `control_root`, or
use the default temporary store. An unbound draft remains readable as data and
cannot execute. Keep the issued references when copying or replanning the
lifecycle.

For example, create the plan and lifecycle from the same initialized value:

```python
plan = plan_from_document(
    planning_input,
    repository_root=repository,
    control_root=external_artifact_root / "run-control",
)
lifecycle_input = {"plan": asdict(plan), "source_state": planning_input["source_state"]}
```

Replace the `plan` placeholders in runtime-operation examples with the emitted
plan; callers do not author control paths or digests. Control files must remain
outside the reviewed repository and cannot traverse symlinks. Admission and
stopping share a run-level lock across journals. Every continuation retains the
binding, so a stop during publication blocks its later launches even when
`journal_path` is absent or points to a new journal.

## Repair Budget

The runtime owns a default budget of **two content-changing repair batches**
after the initial review barrier. One epoch is one serialized batch of source
edits, including optional fixes and required formatting, closed by a content
recapture and `advance-after-mutation`. Individual findings, formatting commands,
red/green checks, metadata staging, commits, pushes, and waiting for CI do not
increment this counter. A no-content-change batch is not a repair epoch. Epochs
must be consecutive; replanning, continuation, or publication never resets them.

Before editing, run `review-control` with `action: begin-repair` and
`authorization: review-and-fix`. Use the lifecycle `plan` and `source_state`, an
external `artifact_store`, and these CLI arguments:

```sh
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/review_graph_runtime.py" \
  review-control --input <request.json> \
  --journal <execution.jsonl> --dispatches <dispatches.json> \
  --current-capture <capture.json> --output <control-result.json>
```

Set `SKILLS_ROOT` to the installed skills directory, as in the
[bootstrap starter](bootstrap-starter.md).

`repair-authorized` returns the next ordinal. Finish compatible edits together;
do not turn each newly discovered optional cleanup into another batch. Pass
`journal_path` and `dispatches_path` to `advance-after-mutation` so it collects
accepted evidence automatically; also retain historical reuse sources. Its
per-node decisions explain which changed or uncertain inputs require inspection.
Keep a branch review's captured merge base fixed across repairs.

At exhaustion, the control operation publishes an immutable stopped continuation
and a terminal marker for its shared budget generation. It also attempts a marker
copy beside the old journal. It reports remaining findings, incomplete
nodes, and a partial proof status. Disclose deferred optional cleanup, affected
verification still needed, and required scientific or CI obligations. Do not
bootstrap another run or renumber epochs to bypass the boundary.

Further source edits require an explicit user budget extension. Use
`action: extend-budget`, positive `additional_epochs`, and the user's exact
`user_authorization`. Follow the returned continuation paths together. This
preserves the counter, dispatches, journal history, and accepted evidence;
the original stopped continuation stays stopped. An extension may clear budget
exhaustion but cannot undo an explicit user stop.

The extension creates one child generation and retains the authoritative count
and history. A distinct second grant from the same parent is rejected; further
grants use the returned child lifecycle. The parent remains terminal. Identical
CLI grant retries recover the original child result with a corrected output path.

## Delivery, CI, And Comprehensive Restarts

Track requested fixes delivered, affected verification, hosted CI, and formal
proof completion separately. Committing/pushing fixes, pending CI, and incomplete
proof bookkeeping are not new defects and do not authorize another comprehensive
review. Continue eligible evidence through the authorized commit handoff,
including branch/PR scope, with the original immutable comparison base. Await or
report pending hosted results. A failed CI check can reopen its relevant contract
and necessary validation within the remaining repair budget.

A fresh comprehensive pass requires `review-control` with
`action: authorize-restart` and a `restart_trigger` containing:

- `trigger`: `confirmed-new-defect`, `expanded-source-scope`, or
  `explicit-user-request`.
- `evidence`: the concrete defect, scope delta, or user's request.
- `targeted_verification_insufficient`: why affected-contract verification cannot
  cover this trigger.

The operation records authorization without scheduling any audits itself. Carry
the run-wide lifecycle into any replacement plan; it does not grant more repairs.
Planning inputs use `review_lifecycle` from that continuation and
`planning_purpose: comprehensive-restart`; ordinary repair transitions set
`planning_purpose: repair-verification` themselves. The planner rejects a stopped
run or a comprehensive restart lacking its recorded trigger.
Default repair replanning uses unchanged evidence rather than a comprehensive
restart. Never describe an unfinished fresh pass as a completed formal review.

## Explicit User Stop

Immediately interrupt active worker agents when the user stops the run. Run
`review-control` with `action: stop` and the user's `reason`; it preserves
incomplete evidence and returns `cancel_node_ids`. Cancel every listed worker
using the actual worker tool and terminate active coordinator commands. The
runtime records cancellation obligations; it does not operate agent tools.
Do not wait for an audit to finish before honoring the stop. Scheduling,
fallback, repair, and recovery cannot revive the stopped plan or its old journal.
Report the stopping reason and unfinished obligations with partial status.

A user stop is terminal for the shared run identity, including every extended
generation. Its marker retains the complete immutable control result and receipt
identity. An identical CLI stop retry can recover its cancellation receipt with
a corrected output path. A failed journal-side marker copy cannot forget a
committed run-level stop; output or store failures before that commit preserve
the prior authority.
