# Scholarly DOI Reconciliation

Use only for completed DOI checks whose titles and authors match and whose
publication years disagree with primary publisher or journal archive records.
This is a reviewer judgment backed by retained evidence, not automatic publisher
authentication. Inspect the primary URL, DOI, edition, title, authors, and date
before recording the disposition. Network failures and identity mismatches
remain blockers. Do not change correct dates merely to match resolver metadata.

Keep the exit-1 validator and its original JSON artifact intact. Add
`scholarly_doi_resolution` to its synthesis `validation_reconciliation` row,
retaining `result: "failed"`. Follow the
[synthesis schema](schemas/synthesis-payload-v1.schema.json). Each failed
execution needs exactly one check; each year-only DOI/line occurrence needs
exactly one disposition. A check has this shape:

```json
{
  "execution_index": 0,
  "original_report": "/proof-store/original-dois.json",
  "occurrences": [{
    "doi": "10.24033/rhm.30",
    "line": 17,
    "field": "year",
    "resolver_field": "resolved_year",
    "resolver_value": "2018",
    "disposition": "retain-local-publication-year",
    "reviewer": "reviewer identity",
    "reason": "The journal record agrees with the captured bibliography.",
    "primary_record": {
      "path": "/proof-store/numdam-record.txt",
      "digest": "sha256:<actual content digest>",
      "url": "https://www.numdam.org/articles/10.24033/rhm.30/",
      "authority": "journal-archive",
      "retrieved_on": "2026-10-07",
      "doi": "10.24033/rhm.30",
      "title": "La méthode de Cholesky",
      "authors": ["Brezinski"],
      "publication_year": "2005",
      "excerpt": "<retained primary text supporting DOI, title, authors, and year>"
    }
  }]
}
```

The enclosing resolution requires `reason` and `checks`. Paths and excerpts in
this example are placeholders. Save actual primary text or HTML outside the
repository; the digest binds its exact bytes. The excerpt must occur in those
bytes after HTML/punctuation normalization and support all the extracted fields.
The verifier requires strong title overlap, all resolved authors, a year-only
checker disagreement, and the primary year present in the captured local entry.
It does not approve corrections to titles, authors, DOI identities, or editions.
`resolver_field` defaults to `resolved_year`. When the selected year agrees with
the bibliography but other resolver publication fields conflict, name the
disagreeing `issued`, `published-print`, `published`, or `published-online` field
and its retained value. The local and disputed years must differ.

New checker JSON retains the Markdown bytes. `compile-node` binds them to the
validator's source capture and retains the capture in metadata. For a historical
report, a check may instead supply `source_evidence` with `capture_path`,
`capture_digest`, `bibliography_path`, and `bibliography_digest`. Use the already
retained capture and original bibliography bytes; the verifier checks both
digests, the capture's source-state triple, and the captured regular-file identity.
The old checker's exact year-only message is eligible when title/author scores
also pass. Missing retained evidence cannot be reconstructed from today's file
or filled in by altering the original report. This path needs no repeated DOI
check when the historical evidence is sufficient.

For mixed scholarly/software failures, plan canonical CFF checking initially.
If a follow-up is needed, use the existing
[source-preserving expansion](software-doi-reconciliation.md#add-a-canonical-follow-up).
Add `software_verification` to the scholarly check with the accepted follow-up's
`evidence_id`, zero-based `execution_index`, and JSON `report` path. It must use
the same source and DOI occurrences, with unchanged resolved identity; only
software pointers may become `OK` through captured canonical CFF metadata.
The follow-up may retain exit 1 for the same scholarly date disagreements.
Attach a scholarly resolution to that failed validator as well, without a
software verification when its software rows are already `OK`.

Synthesis and final proof verify report and primary evidence digests again.
Readiness can become `ready` only after every failed occurrence and every other
readiness condition is reconciled. Final output exposes
`scholarly_doi_resolutions` and preserves `repository_validation_status: "failed"`.
