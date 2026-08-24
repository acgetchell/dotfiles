# Review Graph Runtime Contract

Use this compact contract for ordinary adaptive, isolated, and mixed execution.
The deterministic planner and runtime compiler enforce the detailed evidence
schema. Do not load the maintainer-facing planning, native-artifact, or report
specifications unless changing those implementations or diagnosing rejection.

## Compact Routing Input

The graph-planning document uses `routing_overrides` instead of a complete
caller-authored `routing_decisions` array. Include the captured scope metadata,
consulted routers, validation requirements, and only semantic routing records:

```json
{
  "catalog_id": "rust.errors",
  "disposition": "selected",
  "reason": "typed error behavior changed",
  "applicability_evidence": ["src/error.rs changes public variants"],
  "review_surface": ["src/error.rs"],
  "owners": ["rust"],
  "validation_requirement_ids": ["rust-tests"]
}
```

Optional selected-record fields are `instruction_paths`, `static_references`,
and `evidence_id` for exact reuse. Do not return router, rule, skill, path,
priority, requirement, or synthesis identity; the planner derives them from the
catalog. Unmentioned candidates become explicit `not-applicable` records.

The planner automatically selects:

- repository surfaces signaled by captured paths
- `repository-independent-review` for a concrete change target
- synthesis for every consulted surface and the repository

Semantic routing may add conservative selections or explicit exclusions, but
may not contradict the repository classifier silently.

Before finalizing consulted routers, inspect the captured diff or baseline
inventory for shared semantic ownership that path classification alone cannot
prove:

- route workflow, recipe, command-documentation, lockfile, and toolchain changes
  to tooling plus every language whose build or validation semantics they alter
- route `Cargo.toml`/`Cargo.lock`, CMake/vcpkg configuration, and
  `pyproject.toml`/`uv.lock` to their language owner plus tooling
- route command or API examples to both their truth-owning language and
  documentation/tooling owner as applicable
- in baseline mode consult each surface present in the tracked inventory; in
  release-readiness mode include every active non-archived document
- resolve ambiguous `.h` or shared configuration ownership from its checked-in
  target or surrounding repository context

Represent these conservative additions as sparse selected overrides for the
repository router. Generate the ordinary routing context with:

```sh
uv run --locked python scripts/review_graph_runtime.py routing-projection \
  --input <captured-paths-and-consulted-routers.json> \
  --output <routing-projection.json>
```

The projection contains every candidate for each consulted router, classifier
signals, path matches, semantic triggers, and a digest. Read a surface
`check-routing.md` only to resolve an ambiguity the projection cannot settle.

## Plan Materialization And Scheduling

After `review_graph_plan.py` accepts the graph, derive dispatch bases once:

```sh
uv run --locked python scripts/review_graph_runtime.py materialize-dispatches \
  --input <plan-source-state-and-store.json> --output <dispatches.json>
```

The input also names the repository root, authorization, state command, and
artifact store. The result binds canonical evidence IDs, artifact paths,
provenance, requirements, validation units, and predecessor evidence. Add only
observed before/after state and the worker payload before compilation.

Keep lifecycle state in one coordinator-owned append-only journal:

```sh
uv run --locked python scripts/review_graph_runtime.py journal-append \
  --input <plan-and-source-state.json> --journal <execution.jsonl> \
  --node-id <node-id> --status <in-flight|accepted|blocked|invalidated>
```

An accepted event also requires `--artifact` and `--metadata`; the runtime
verifies the compiled evidence and binds its identities and digests. Supply
`--reason` for invalidation and for blockers without a compiled artifact.
Invalidating a node deterministically invalidates already-started descendants.
Only the coordinator appends events, serially.

After each event, emit only currently ready dispatches:

```sh
uv run --locked python scripts/review_graph_runtime.py next-ready \
  --input <plan-and-source-state.json> --journal <execution.jsonl> \
  --dispatches <dispatches.json> --output <ready.json>
```

The runtime verifies the journal chain, plan and source-state binding, legal
transitions, artifact-backed acceptance, and dispatch-set digest. It returns
the folded lifecycle view, blockers, waiting nodes, and exact ready dispatches.

## Fresh Worker Dispatch

Create workers with `fork_turns: "none"`. A review dispatch contains only:

- exact repository root, authorization, node ID, mode, and owned paths
- captured fingerprints and state-verification command
- exact skill path and relevant reference paths
- applicable repository instruction paths
- selection reason and validation evidence already accepted for this node
- this `ReviewPayload` schema

Do not send the coordinator journal, unrelated routing records, complete prior
reports, prior conclusions, or proof-format instructions.

## ReviewPayload

Return one JSON object and no compatibility Markdown:

```json
{
  "status": "completed | no-findings | blocked",
  "files_inspected": ["path"],
  "nearby_contract_owners": ["path"],
  "findings": [
    {
      "severity": "P0 | P1 | P2 | P3",
      "location": "path:line",
      "summary": "actionable defect",
      "evidence": "specific violated behavior or contract",
      "remediation": "smallest safe correction"
    }
  ],
  "validation_requirements": [
    {
      "requirement_id": "stable-id",
      "owner": "skill-id",
      "reason": "risk requiring evidence",
      "commands": ["exact command"],
      "working_directory": "/absolute/path",
      "environment": "complete relevant identity",
      "expected_evidence": "observable success condition",
      "dependency_policy": "stop-on-failure | continue-independent"
    }
  ],
  "handoffs": [
    {
      "catalog_id": "catalog.entry",
      "observed_trigger": "new applicability evidence",
      "reason": "why another owner is required",
      "scope": ["path"]
    }
  ],
  "changes": [],
  "limitations": []
}
```

Use an empty array for absent fields. A blocked payload requires a concrete
limitation. `no-findings` requires an empty findings array. The compiler assigns
stable finding, handoff, change, evidence, and artifact identities.

For an authorized fix payload, `changes` contains:

```json
{
  "finding_ids": ["finding-or-incidental-id"],
  "files": ["path"],
  "what_changed": "specific behavior change",
  "why": "evidence-backed reason",
  "contract_preserved": "compatibility or invariant preserved"
}
```

The trusted dispatch, not the worker, records `source_mutated`, exact changed
paths, expected post-fix state, execution location, worker creation, and fresh
context.

## Compilation

Persist the worker JSON, then compile it:

```sh
uv run --locked python scripts/review_graph_runtime.py compile-review \
  --input <dispatch-and-payload.json> \
  --artifact <compiled-result.md> \
  --metadata <compiled-evidence.json>
```

The compiler:

- hashes the dispatched skill and references
- binds expected, before, and after fingerprints
- embeds the canonical compact payload and its digest
- renders the native compatibility artifact
- constructs the evidence envelope
- runs native and envelope acceptance before writing output
- refuses to overwrite an existing output with non-identical bytes

A compilation failure is blocked evidence. Do not repair the artifact manually;
correct the compact payload or trusted dispatch and compile once more.

## SynthesisBundle

Compile the synthesis view from accepted artifacts and compiler metadata:

```sh
uv run --locked python scripts/review_graph_runtime.py synthesis-bundle \
  --input <accepted-evidence-sources.json> \
  --output <synthesis-bundle.json>
```

Each source names `artifact_path`, `metadata_path`, and optionally `kind`.
The runtime verifies both evidence gates and the artifact digest, then derives
the normalized record from the embedded canonical payload. Callers never
transcribe findings or mappings into the bundle.

The bundle contains source identity, accepted evidence and artifact identities,
requirements, findings, validation status, handoffs, and limitations. It is
sorted and hashed deterministically. Synthesis receives this bundle rather than
complete native reports. The proof verifier still reads and verifies every raw
artifact independently.

## ValidationPayload

Graph-dispatched validators read only
`review-validator/references/graph-dispatch.md` and return its compact payload.
Persist the payload, then compile it:

```sh
uv run --locked python scripts/review_graph_runtime.py compile-validation \
  --input <validation-dispatch-and-payload.json> \
  --artifact <compiled-validation.md> \
  --metadata <compiled-validation-evidence.json>
```

The trusted dispatch carries the planner-owned `ValidationUnit`, exact skill
and reference paths, expected/before/after fingerprints, execution location,
fresh-context evidence, and artifact/evidence IDs. The payload contains only
command outcomes, approved artifact identities, and limitations. The compiler
derives digests, mappings, ledger export, and canonical machine evidence.

## Persistence And Reporting

Persist outside the reviewed repository:

- capture manifests and routing input
- sparse overrides and the planner-emitted expanded `routing_decisions` ledger
- compact worker payloads and compiler metadata
- compiled review and native independent-review artifacts
- validation results and artifact digests
- synthesis bundles and synthesis results
- invalidation history, manifest, and final proof

The compact user report links or names this store. Inline exhaustive tables only
for a requested proof dump or when their exceptional rows explain incompleteness.

Finalize from the accepted plan, source state, and persisted evidence sources:

```sh
uv run --locked python scripts/review_graph_runtime.py finalize-proof \
  --input <finalization-input.json> --output <proof-result.json>
```

The finalizer derives requirement/node mappings, accepted evidence sets,
manifest entries, digests, and the repository proof, then runs the trusted
bundle verifier. Exit status is nonzero and `status` is `incomplete` when any
handoff or other gate remains unresolved; do not hand-author or patch the proof.
