# Applicable Scope And Partial Audit Continuation

Use this procedure when a source audit has completed some inspection and needs
to finish the remaining paths on unchanged inputs. A wrong-checklist judgment
instead uses [audit replacement](state-transitions.md#replace-an-invalidated-audit).

## Classify Exclusions Before Dispatch

Apply the user's scope and the selected skill's repository policy before
dispatch. Historical status requires evidence from the file or repository
instructions; a directory name alone does not establish exclusion. For example,
the citation skill excludes historical archives unless archive maintenance was
requested. Generated changelog archives can receive the same classification
when the applicable policy excludes them. Active documentation still requires
substantive inspection.

Add `review_scope_exclusions` to planning input or baseline starter choices:

```json
{
  "review_scope_exclusions": [
    {
      "catalog_id": "docs.citations",
      "path": "docs/archive/CHANGELOG.md",
      "reason": "The header marks this generated changelog as historical; AGENTS.md excludes archive citation maintenance.",
      "policy_source": "AGENTS.md"
    }
  ]
}
```

Each record requires an exact captured path, selected specialist, nonempty
reason, and policy source. The source must be that specialist's skill or one of
its applicable `instruction_paths`; planning resolves repository-relative and
`$SKILLS_ROOT` paths. The coordinator must read and apply that policy, including
any user override. The runtime verifies the binding, not the truth of the
semantic classification.

The planner removes these paths from that specialist's substantive ownership
and preserves every classification in the plan, dispatch and final proof. Other
specialists keep their own coverage obligations. If no specialist owns a path,
the separate whole-repository `captured_path_dispositions` assessment is still
required. Do not use another specialist's inspection to discharge this skill's
contract. In particular, selected whole-repository Rust style coverage includes
source, tests, examples and nested benchmark helpers; missing paths require
explicit policy-backed exclusions. Focused scope keeps its selected boundary.

## Continue Published Partial Evidence

Publish the actual `files_inspected`, findings, validation requirements and
handoffs. Give every omitted owned path one `scope_limitations` reason, using
`blocked` when inspection remains incomplete. Do not claim that classification
was a full read or replace an accepted artifact. Unclassified limitations and
unresolved semantic uncertainty require their own resolution; this operation
only continues source inspection.

Finish compiling other in-flight work and capture the current source. Build a
request from the current lifecycle's `plan`, `source_state` and any
`external_metadata_transitions`. Add an external `artifact_store`, the partial
audit's `node_id`, and a concrete `reason`. If exclusions were discovered after
publication, include `review_scope_exclusions` for those omitted paths, using
the exact bound skill/instruction paths from the dispatch as `policy_source`.
Already inspected paths cannot be reclassified to remove findings.
If removing this owner leaves an archive globally unassigned, also supply its
reasoned `captured_path_dispositions` entry. The continuation recomputes the
whole-repository inventory; another specialist's ownership remains intact.

Set `REVIEW_PYTHON` and `REVIEW_RUNTIME` from the run's generated commands and
run from the reviewed repository:

```sh
"$REVIEW_PYTHON" "$REVIEW_RUNTIME" continue-partial-audit \
  --input <partial-request.json> --journal <execution.jsonl> \
  --dispatches <dispatches.json> --current-capture <capture.json> \
  --output <continuation-result.json>
```

The operation requires compiled partial evidence, a content-bound capture equal
to the original source state, unchanged instructions and dependencies, and
quiescent execution. It also accepts an older `completed` payload with truthful
scope limitations. It rejects uncompiled blocks, source changes, overlapping
classifications, missing omission reasons and stopped runs. If the frozen
runtime predates this operation, use an updated runtime with the original
lifecycle, captures and frozen skill paths; never edit the old snapshot or plan.

Follow the returned lifecycle, dispatch, journal and capture paths together.
The original journal, compiled evidence and sealed payload stay immutable and
digest-bound. The old plan is retired. The affected audit and its dependent
syntheses receive fresh identities; unrelated accepted audits and validators
retain their original evidence. Identical retries return the saved result.

The new worker receives a bound `coverage_reuse` view. Inspect only its `recheck`
paths. Record those actual reads in `files_inspected`; do not list reused paths
again. The compiler retains completed findings with their original evidence
attribution. Copy the original validation requirements and handoffs exactly
from the view, adding any newly discovered obligations. The operation does not
waive validation or convert a failed check into success.

Missing active inspection still rejects `no-findings`. Findings require
`completed`; inherited findings count too. If all remaining paths are valid
exclusions, the fresh worker may publish with no new source reads, after
reconciling the retained obligations. Further partial continuations require new
inspection or new policy classification; they cannot repeat without progress.
Repair counters, worker budget and reserve remain unchanged, and ordinary
admission capacity and stop rules still apply. No source edit, Git mutation or
whole-repository restart is required or authorized by this operation.
