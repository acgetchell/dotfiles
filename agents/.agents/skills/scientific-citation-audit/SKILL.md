---
name: scientific-citation-audit
description: Audit scientific/research-software citations for existence, bibliographic correctness, relevance, and credit alignment. Use when reviewing REFERENCES.md, CITATION.cff, paper bibliographies, DOI links, algorithm provenance, source-code citations, literature-review completeness, or claims that a scientific crate gives appropriate credit for algorithms, data structures, numerical methods, topology, benchmarks, and research-software practice.
---

# Scientific Citation Audit

Use this skill to verify that a scientific repository credits the right work and does not cite nonexistent, malformed, or irrelevant sources. Treat citation integrity as part of scientific correctness: a DOI that resolves to the wrong paper is a finding even when the link itself is live.

## Audit Workflow

1. Read repository guidance first: agent instructions, documentation rules, and any paper/release guidance that says how references are owned.
2. Inventory the literature surface:
   - `REFERENCES.md`, `CITATION.cff`, paper manuscripts, README citation sections, active docs, and public API/module docs.
   - Exclude archived historical docs unless the user explicitly asks for archive maintenance.
3. Map claims to credit:
   - Search for algorithm/data-structure/method names in code and active docs.
   - For each implemented or advertised method, check that the nearest source/module docs mention the relevant provenance or point to `REFERENCES.md`.
   - Check that `REFERENCES.md` has the specific source for the algorithm or data structure, not only a broad textbook when a primary paper is known and relevant.
4. Validate references mechanically and intellectually:
   - Verify DOI/link existence.
   - Verify DOI metadata title/authors/venue/year match the stated citation.
   - Verify the cited work is relevant to the claim being made.
   - Prefer primary sources for algorithmic credit; keep secondary textbooks/manuals as background or implementation-context references.
5. Report or fix drift:
   - Missing credit: implementation/docs name a method but `REFERENCES.md` lacks an appropriate source.
   - Misplaced credit: `REFERENCES.md` has a source but code/docs that implement the method do not cite or point to it.
   - Bad citation: DOI/link dead, malformed, or resolves to unrelated metadata.
   - Orphan reference: source exists in `REFERENCES.md` but no active code/doc cites or motivates it.

## DOI Metadata Check

Run the bundled checker when auditing Markdown references with DOI labels:

```bash
uv run <skill-directory>/scripts/validate_reference_dois.py REFERENCES.md
```

Resolve `<skill-directory>` from the loaded `SKILL.md`. When the active repository does not use `uv`, run the dependency-free script through its documented isolated Python environment rather than installing into a system interpreter.

The script extracts DOI labels from Markdown, queries DOI content negotiation for CSL JSON metadata, and compares the resolved title against the surrounding bibliography entry. Use `--json` for machine-readable output.

Network access is required. If the environment blocks network calls, request approval/escalation and explain that citation validation must query DOI/Crossref/publisher metadata.

A passing network check is not enough. Manually inspect low-confidence matches, primary algorithm references, and every citation that supports a scientific or implementation claim.

## Domain References

Read [`references/computational-geometry.md`](references/computational-geometry.md) only when auditing computational geometry, triangulation, mesh/topology, spatial-index, or robust-predicate credit. Do not load it for unrelated scientific fields.

## Editing Guidance

When fixing references:

- Preserve the repository's existing reference format.
- Prefer DOI links only after verifying DOI metadata matches the cited work.
- Use angle links or percent-encoded URLs when DOI strings contain parentheses or other Markdown-sensitive characters.
- Keep `REFERENCES.md` as the bibliography owner, but add local source/doc pointers near the algorithm that uses the citation.
- Do not update generated changelogs by hand.

## Output Format

### Citation Surface Inspected
- Files and active docs reviewed.

### Mechanical Validation
- DOI/link validation command and result.
- Dead, malformed, or metadata-mismatched references.

### Credit Alignment
- Algorithm/data-structure claims with correct credit.
- Missing, weak, or misplaced credit.

### Changes Made
- Files edited and why.

### Validation
- Documentation/config validator run, or reason it was not run.

### Follow-ups
- Optional literature additions, paper-reading tasks, or citation questions left for the maintainer.
