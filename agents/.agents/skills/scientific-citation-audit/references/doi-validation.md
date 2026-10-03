# DOI Metadata Validation

Read this reference only when auditing Markdown DOI labels or verifying DOI
metadata.

Run the bundled checker:

```bash
uv run <skill-directory>/scripts/validate_reference_dois.py REFERENCES.md
```

Resolve `<skill-directory>` from the loaded `SKILL.md`. When the active
repository does not use `uv`, run the default dependency-free check through its
documented isolated Python environment rather than installing into a system
interpreter.

The script extracts DOI labels from Markdown, queries DOI content negotiation
for CSL JSON metadata, and compares the resolved title with the surrounding
bibliography entry. Use `--json` for machine-readable output.

A badge-only paragraph or bare DOI link reports `INSUFFICIENT_CONTEXT` when its DOI resolves:
missing author/title/year context is not contradictory metadata. Compare the
resolved identity with `CITATION.cff` or primary metadata. This outcome retains
exit status 1 (manual verification needed), not a successful bibliographic match.
Resolution failures remain `FAIL`; contradictory reference text remains `MISMATCH`.

For project software links, supply canonical metadata explicitly:

```bash
uv run --with PyYAML <skill-directory>/scripts/validate_reference_dois.py README.md --citation-cff CITATION.cff --json
```

Use the repository's locked environment when it already provides PyYAML. This
optional mode reads the root software `doi`, `title`, `authors`, and
`date-released` according to the
[CFF schema guide](https://github.com/citation-file-format/citation-file-format/blob/main/schema-guide.md).
It does not substitute `preferred-citation` or a DOI from `references` or
`identifiers`. Missing or malformed canonical fields produce exit 2.

Only links without bibliographic claims can use canonical identity. A small
set of citation-pointer words, including `CITATION.cff`, is recognized; unknown
prose keeps the ordinary bibliography checks. Scholarly references and local
author/title/year claims retain those checks. Canonical comparison requires the
linked and resolved DOI, normalized full title, all author family/entity names,
and release year to match. Missing resolved fields still require review.

JSON rows retain resolved metadata and a Markdown path/content digest. Canonical
rows additionally retain `local_status: INSUFFICIENT_CONTEXT` and
`canonical_software` with the CFF path, content digest, checked identity, and
exact bytes in `content_base64` for verification against the source capture.
A successful canonical check is a new execution; it never rewrites an earlier
nonzero result. In review-graph, preserve both reports as declared validation
artifacts and follow
[software DOI reconciliation](../../review-graph/references/software-doi-reconciliation.md)
to reconcile readiness without deleting badges or duplicating citation metadata.

Network access is required. If the environment blocks network calls, request
approval and explain that validation must query DOI, Crossref, or publisher
metadata.

A passing network check is not enough. Manually inspect low-confidence matches,
primary algorithm references, and every citation supporting a scientific or
implementation claim.
