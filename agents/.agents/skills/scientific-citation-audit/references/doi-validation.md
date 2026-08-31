# DOI Metadata Validation

Read this reference only when auditing Markdown DOI labels or verifying DOI
metadata.

Run the bundled checker:

```bash
uv run <skill-directory>/scripts/validate_reference_dois.py REFERENCES.md
```

Resolve `<skill-directory>` from the loaded `SKILL.md`. When the active
repository does not use `uv`, run the dependency-free script through its
documented isolated Python environment rather than installing into a system
interpreter.

The script extracts DOI labels from Markdown, queries DOI content negotiation
for CSL JSON metadata, and compares the resolved title with the surrounding
bibliography entry. Use `--json` for machine-readable output.

A badge-only paragraph reports `INSUFFICIENT_CONTEXT` when its DOI resolves:
missing author/title/year context is not contradictory metadata. Compare the
resolved identity with `CITATION.cff` or primary metadata. This outcome retains
exit status 1 (manual verification needed), not a successful bibliographic match.
Resolution failures remain `FAIL`; contradictory reference text remains `MISMATCH`.

Network access is required. If the environment blocks network calls, request
approval and explain that validation must query DOI, Crossref, or publisher
metadata.

A passing network check is not enough. Manually inspect low-confidence matches,
primary algorithm references, and every citation supporting a scientific or
implementation claim.
