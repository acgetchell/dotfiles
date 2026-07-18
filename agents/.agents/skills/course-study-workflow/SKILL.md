---
name: course-study-workflow
description: "Create and maintain Markdown-first course study artifacts from lectures, slides, readings, assignments, notes, and practice questions. Use for outlines, summaries, quiz or exam preparation, practice assessments, repair notes, formula sheets, and derived LaTeX, PDF, DOCX, or slide materials."
---

# Course Study Workflow

Create and maintain study artifacts from course materials such as lecture slides, textbooks, readings, assignments, notes, and practice questions.

Use this workflow for quizzes, midterms, finals, oral presentations, qualifying exams, cumulative review, and allowed exam-aid preparation.

## Core Workflow

1. Identify the exam or study scope.
2. Build lecture or topic outlines.
3. Convert outlines into study summaries.
4. Generate practice quizzes or exams.
5. Grade responses.
6. Add repair material for weak concepts.
7. Synthesize multiple summaries into a cumulative concept summary.
8. Condense the cumulative summary into an allowed exam sheet, formula sheet, topic sheet, or oral review sheet.

## Source Of Truth

Treat the Markdown outline as the authoritative working document.

Treat rendered documents such as LaTeX, PDF, DOCX, or slides as derived artifacts.

Unless the user explicitly says otherwise:

- Update the Markdown outline first.
- Regenerate or patch rendered documents from the outline.
- Preserve user corrections, quiz-repair material, and instructor-specific emphasis.
- Do not directly edit rendered study notes when the outline should drive them.

## File Pattern

Prefer a `Study/` directory when the repository or course folder already uses one:

```text
Study/
  LectureN-outline.md
  LectureN.tex
  TopicName-outline.md
  TopicName.tex
  ExamSummary.tex
  ExamSheet.tex
  PracticeExamN.md
  QuizRepair.md
```

Use course-specific names when helpful:

- `MidtermSummary.tex`
- `FinalSummary.tex`
- `FormulaSheet.tex`
- `TopicSheet.tex`
- `OralExamReview.md`

## Outline Format

Preserve the order of the source material unless the user asks for synthesis by topic.

Include, when applicable:

- Source identifier
- Scope
- Overall narrative
- Section, slide, page, or reading ranges
- Purpose
- Key ideas
- Definitions
- Mental pictures
- Why this matters
- Dependencies
- Common confusions
- Exam traps
- Likely quiz or exam questions
- User questions while reading
- Repair notes from quizzes or practice exams

## Style Rules

- Prefer conceptual understanding over transcription.
- Keep source order during initial lecture summaries.
- Use synthesis order only for cumulative summaries.
- Add `Common Confusion` sections when the user asks clarification questions.
- When the user asks a clarification question during lecture review, determine whether the explanation reveals a conceptual gap in the source material. If so, incorporate the clarification into the outline as `Common Confusion`, `Mental Picture`, `Why This Matters`, or `Exam Trap` material rather than leaving it only in the conversation.
- Add `Exam Trap` sections for distinctions likely to appear in multiple-choice or short-answer questions.
- Include formulas only when useful for recognition, reasoning, or allowed exam sheets.
- When formulas are included, add plain-English intuition.
- Preserve instructor emphasis over textbook order when they differ.
- Use textbooks as clarification and gap-filling unless the user requests a full reading summary.

## Summary Documents

When generating a study summary from an outline:

- Follow the outline structure.
- Preserve source order.
- Include section numbers, slide ranges, page ranges, or reading references when available.
- Convert outline bullets into dense but readable study notes.
- Keep key ideas, mental pictures, why-this-matters notes, definitions, common confusions, exam traps, and quick triggers.
- Make the summary suitable for later compression into a cumulative exam review.

## Practice Quizzes And Exams

Generate practice questions in the expected exam format when known.

Possible formats:

- Multiple choice
- Multiple answer
- True/false
- Fill in the blank
- Short answer
- Essay
- Concept matching
- Diagram interpretation
- Calculation

Emphasize:

- High-level concepts
- Definitions
- Architecture or taxonomy distinctions
- Common confusions
- Instructor-emphasized material
- Material the user previously missed

After grading, produce:

- Score
- Missed concepts
- Correct answers
- Repair notes
- Suggested outline edits
- Suggested exam-sheet additions

## Repair Passes

When the user misses questions or identifies confusion:

- Add a repair subsection to the relevant outline.
- Keep repairs near the original source topic.
- Mark high-yield repairs for later extraction.
- Update the rendered summary only after the outline is corrected.

## Cumulative Summaries

Generate cumulative summaries from final topic or lecture summaries.

Organize by concepts rather than source order unless the user requests otherwise.

Prioritize:

- Definitions
- Taxonomies
- Comparisons
- Mental pictures
- Dependencies
- Common confusions
- Exam traps
- Quiz repair material
- High-yield examples
- Instructor-specific terminology

## Allowed Exam Sheets

Generate allowed exam sheets from the cumulative summary.

Adapt to the allowed format:

- one page
- two pages
- formula sheet
- topic sheet
- handwritten sheet
- open-note index
- oral defense crib sheet

Prioritize:

- Compact definitions
- Core formulas
- Taxonomy tables
- Model or method distinctions
- Error-prone concepts
- Mnemonics
- Exam traps
- User-specific weak spots

Use dense formatting and minimize prose.

## Final Exam Mode

For cumulative finals:

- Merge midterm material with post-midterm material.
- Prioritize connections across the course.
- Preserve prior quiz repairs.
- Mark concepts that recur across multiple lectures.
- Identify old material likely to reappear because it supports later topics.

## Interaction Pattern

When working with the user:

1. Ask what material is in scope.
2. Confirm the deadline and allowed exam aids.
3. Build or update outlines first.
4. Generate summaries.
5. Move quickly to retrieval practice.
6. Repair only what practice reveals.
7. Freeze source summaries before final practice unless there is a genuine error.
8. Patch the allowed exam sheet based on missed questions.
