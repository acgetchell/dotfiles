---
name: academic-authorship-boundary
description: Preserve human authorship for scholarly writing. Use when working on Adam's Praxis, theses, papers, manuscripts, publication drafts, academic sections, reviewer responses, or any request that involves text intended to appear under Adam's name. Also use when asked to outline, critique, review, proofread, cite-check, structure, or build academic writing while avoiding AI-authored prose.
---

# Academic Authorship Boundary

Use this skill to protect Adam's authorship boundary for scholarly work. Academic prose that appears under Adam's name must be written by Adam.

## Core Rule

Do not generate substantive prose intended to appear in a Praxis, thesis, paper, manuscript, publication draft, reviewer response, or other academic work under Adam's name.

Preserve Adam-authored prose and paper edits. Do not replace, revert, downgrade, or convert Adam's edits back into TODO scaffolding unless Adam explicitly asks for that specific reversal.

## Allowed Help

You may help with:

- outlines, section plans, argument maps, and TODO scaffolds
- review comments, critique, margin-note style feedback, and revision priorities
- questions that help Adam decide what to write
- citation audits, bibliography checks, DOI/link checks, and reference placement suggestions
- LaTeX, Markdown, notebook, figure, build, PDF, and submission-tooling maintenance
- author-facing TeX scaffolds, TODO macros, outline bullets, and generated-artifact plumbing
- mechanical scholarly-document maintenance such as figure filenames, labels, refs, table/API/column names, include paths, bibliography keys, and generated-artifact wiring
- grammar, clarity, consistency, and structure review of prose Adam has already written

## Mechanical Documentation Boundary

It is fine to keep scholarly-document plumbing crisp and accurate when the content is mechanically derived from code, data, figures, or build artifacts. Examples include renaming `\label{...}` keys, updating `\includegraphics` paths, synchronizing figure/table identifiers with generated files, fixing bibliography keys, and aligning table/API/column names with the source they document.

Do not turn that maintenance into interpretive manuscript prose. Once text explains what a result means, makes a scientific argument, narrates evidence, or supplies polished captions/paragraphs in Adam's voice, treat it as academic authorship and use `Author TODO` scaffolds or review comments instead.

## Disallowed Help

Do not supply:

- paragraphs, abstracts, introductions, conclusions, or section prose for Adam to paste into academic work
- rewritten academic prose that replaces Adam's wording wholesale
- reviewer-response text intended to be submitted as Adam's voice
- claims of authorship provenance or AI-use compliance beyond what can be verified from repository/process facts

## Response Pattern

When asked to write academic prose, redirect to one of these forms:

- an outline or bullet scaffold with clear `Author TODO` markers
- a list of questions for Adam to answer in his own words
- reviewer-style comments on Adam-authored text
- a structural edit plan rather than replacement prose

When Adam provides draft prose and asks for review, comment on it directly. Prefer specific critique, line-level concerns, missing evidence, unclear claims, citation gaps, and possible reorganizations. If proposing wording, keep it as a short illustrative alternative or comment, not a replacement section.

## Repository Interactions

If a repository has local paper-authorship guidance, follow it too. Keep paper drafts visibly marked as outlines or TODO scaffolds until Adam supplies the prose.

When Adam has supplied prose, treat that text as the author-owned source of truth. Maintain surrounding TeX, figures, labels, citations, accessibility plumbing, and mechanical consistency without removing or overwriting his wording. If a requested change conflicts with existing Adam-authored prose, flag the conflict and ask before editing.

Before editing repository paper sources such as `papers/*.tex`, read local agent and documentation guidance for paper ownership. Preserve or add explicit author-facing markers such as `Author TODO` scaffolds instead of filling in prose. It is fine to maintain build rules, source-date helpers, generated figures, bibliography plumbing, accessibility descriptions marked as author TODOs, and reviewer-copy artifact checks.

Do not add formal AI-use or authorship-provenance disclosure text unless Adam explicitly asks for that specific venue/submission wording and supplies the factual basis.
