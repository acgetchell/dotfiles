# Software DOI Reconciliation

Load only when an executed DOI validator needs canonical software metadata, or
when synthesizing that validator and its canonical follow-up. Prefer planning
`validate_reference_dois.py <Markdown> --citation-cff <CITATION.cff> --json`
initially when auditing project software links. See the
[checker contract](../../scientific-citation-audit/references/doi-validation.md).

An exit-1 DOI report can reflect missing inline metadata rather than a
contradictory citation. This path preserves that failed execution and obtains
a separate passing canonical check on the same captured source state.
It does not use launch recovery, alter accepted payloads, or mark the original
validator passed. Other failures still block readiness.

## Add A Canonical Follow-Up

Keep the original JSON report as a declared validator artifact with a
`content-sha256-v1` digest and an absolute path in its execution's
`artifact_paths`. If the original execution did not retain verifiable JSON,
this reconciliation is unavailable; do not manufacture a historical report.
Keep the native evidence, metadata, journal, and original report intact.

After workers finish, call `reconcile-validation-requirements` with its normal
`plan`, `source_state`, `artifact_store`, journal, dispatches, and current capture.
Supply a new required `validation_requirements` object using the full planning
schema and an additional binding:

```json
{
  "software_doi_rechecks": [{
    "requirement_id": "software-doi-canonical",
    "evidence_id": "validation:original-node",
    "execution_index": 0,
    "original_report": "/proof-store/original-dois.json"
  }]
}
```

Indices are zero-based within the accepted validator's `executions`. Each new
requirement must contain exactly one checker command for the original Markdown
input, adding `--citation-cff` and keeping `--json`. Use explicit argument values
and absolute working directories; an optional final `> <report-path>` is
supported. Shell pipelines and compound commands are not reconciliation inputs.
Declare output artifacts and isolation according to the existing validator
contract; when running in an isolated output directory, pass absolute paths to
the original Markdown and CFF. Keep both inputs in the captured source state.
The canonical checker report retains the CFF bytes. `compile-node` binds those
bytes to the regular-file identity in its source capture and retains that capture
for evidence reloads. Reports without retained bytes or a matching capture cannot
justify readiness; rerun the canonical check to obtain that evidence.

Follow the returned continuation paths. Accepted audits and validators remain;
only the additional check and downstream syntheses run. A legacy `MISMATCH`
may justify a recheck, but cannot by itself justify readiness. No readiness
decision is made during this expansion.

## Synthesis And Final Proof

Use the accepted reports to add `software_doi_resolution` to the original
validator's `validation_reconciliation` item, retaining `result: "failed"`:

```json
{
  "reason": "The links contain no bibliographic claims; canonical software identity matches.",
  "checks": [{
    "execution_index": 0,
    "original_report": "/proof-store/original-dois.json",
    "verification_evidence_id": "validation:canonical-node",
    "verification_execution_index": 0,
    "verification_report": "/proof-store/canonical-dois.json"
  }]
}
```

Account for every failed execution exactly once. The verifier checks both
reports against their accepted artifact digests, the same observed source
state and Markdown input, every DOI/line occurrence, unchanged resolved metadata,
and passing canonical identity whose CFF digest matches the captured bytes.
Reconciliation never compares that digest with the current CFF file.
A formerly failed occurrence must now have
`local_status: "INSUFFICIENT_CONTEXT"`, never a contradictory bibliography.
Missing metadata, wrong identities, resolution failures, other failed commands,
unexecuted commands, changed report bytes, and stale state cannot be excused.

Synthesis may inspect these specific DOI JSON artifacts; it still must not run
validators or reload complete predecessor review artifacts. The proof verifier
rechecks the binding at finalization. Final output preserves
`repository_validation_status: "failed"` and exposes `software_doi_resolutions`;
`repository_readiness` may be `ready` only when this reconciliation and all other
readiness conditions hold. Neither history nor source state is rewritten.
