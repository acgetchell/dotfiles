# Grouped Lane Scheduling

Read when selecting adaptive grouped or declared mixed work after routing.
`schedule-ready` selects one coordinator audit alongside available worker lanes.
Add an external `artifact_store`, optional `worker_capacity` (`source`,
`concurrent_worker_limit`, `active_workers`), and pending `reserved_node_ids` to
the lifecycle input. The worker limit excludes the coordinator: four total agent
slots means three worker lanes plus one coordinator lane.

Count completed workers whose slots remain occupied in `active_workers`;
completion alone does not prove release. Use a current authoritative aggregate
surface or exact host occupancy accounting, never task content or throwaway
creation probes. Omit capacity when uncertain. This scheduling metadata does not
require the isolated capability gate.

```sh
uv run --locked python scripts/review_graph_runtime.py schedule-ready \
  --input <schedule-request.json> --journal <execution.jsonl> \
  --dispatches <dispatches.json> --current-capture <capture.json> \
  --output <schedule-result.json>
```

The compact receipt supplies selected dispatch references, deferred IDs, pending
reservations, capacity state, and one digest-bound continuation. Follow all
returned lifecycle/dispatch/journal/capture paths together. Its `schedule_input_path`
carries pending reservations into the next scheduling request; remove only
explicitly canceled reservations. Journal-bound started/accepted work drops out
automatically. Refresh capacity in a new request each time; the generated input
omits the prior snapshot rather than assuming it remains current.

Use `preflight_blocked_nodes` for unstarted validators whose execution preflight
is blocked. These holds persist in the continuation and receipt, consume no
capacity, and keep independent audits eligible. They cannot overlap reservations.
See [validation preflight](validation-preflight.md) for release and recovery.

A reservation is not a creation receipt: append `in-flight` only after a worker
actually starts, or immediately before the selected coordinator audit starts.
At most one coordinator lane runs. Dependency-ready, read-only syntheses share
available worker slots with other read-only nodes. Each surface synthesis waits
for its own predecessors; repository synthesis waits for every required surface
result. Reservations and in-flight syntheses consume capacity without a shared
execution lock. Their bound payloads and journal acceptance retain the ordinary
provenance checks.

Validators and fixes remain serialized against all other work. When no work is
active and host slots remain full, synthesis, validation, or fixes may execute
on the coordinator too. Independent review stays on a worker.

Scheduling preserves every node, dependency, command policy, source identity,
and accepted artifact. Revised dispatches retain immutable ancestry; the
coordinator publication preflight binds its revised input. Coordinator evidence
always records `worker_created: false` and `fresh_context: false`.

Known full capacity returns no worker dispatch and selects a ready coordinator
audit without failed spawns, waits, or fabricated failures. Unknown capacity
permits one speculative worker lane alongside the coordinator. When no eligible
lane is available, preserve deferred work and wait for genuine lifecycle progress.
Follow [creation-failure handling](runtime-safety.md#journal-and-fallback) for
the bounded race/uncertainty retry and unexpected-error fallback.

`schedule-ready` rejects isolated and isolated-only plans; keep their existing
epoch/failure/resume behavior. Explicit coordinator locations are also rejected
during isolated materialization.
