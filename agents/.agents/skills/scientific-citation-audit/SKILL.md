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

Read [`references/doi-validation.md`](references/doi-validation.md) only when
auditing Markdown DOI labels or verifying DOI metadata. A live link alone is
not evidence that the citation identifies the claimed work.

## Domain References

Read [`references/computational-geometry.md`](references/computational-geometry.md) only when auditing computational geometry, triangulation, mesh/topology, spatial-index, or robust-predicate credit. Do not load it for unrelated scientific fields.

## Editing Guidance

When citation fixes are explicitly authorized, read
[`references/editing-workflow.md`](references/editing-workflow.md) before
editing. Do not load it for review-only work.

When invoked directly without an exact parent result contract, read
[`references/standalone-report.md`](references/standalone-report.md).
Review-graph and documentation-orchestrator dispatches already own reporting.
