---
name: course-study-workflow
description: "Create and maintain Markdown-first course study artifacts from lectures, slides, readings, assignments, notes, and practice questions. Use for outlines, summaries, coverage audits, quick-recall sheets, retrieval drills, point-weighted professor-style practice assessments, error classification and repair, cumulative review, allowed exam aids, and derived LaTeX, PDF, DOCX, or slide materials."
---

# Course Study Workflow

Create and maintain study artifacts from course materials such as lecture slides, textbooks, readings, assignments, notes, and practice questions.

Use this workflow for quizzes, midterms, finals, oral presentations, qualifying exams, cumulative review, and allowed exam-aid preparation.

## Core Workflow

1. Identify the exam or study scope.
2. Build lecture or topic outlines.
3. Convert outlines into study summaries.
4. Audit coverage against the original slides, readings, and instructor materials.
5. Generate quick-recall artifacts.
6. Run rapid retrieval drills.
7. Administer professor-style, point-weighted practice assessments.
8. Report question accuracy and point-weighted score.
9. Classify each error before selecting a repair.
10. Re-test demonstrated weaknesses with changed wording.
11. Synthesize summaries and retrieval repairs into a cumulative concept summary.
12. Condense the cumulative summary into an allowed exam sheet, formula sheet, topic sheet, or oral review sheet.

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
  LectureN-coverage-audit.md
  LectureN-quick-recall.md
  LectureN-retrieval-quiz.md
  LectureN.tex
  TopicName-outline.md
  TopicName.tex
  ExamErrorLog.md
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
- Preserve canonical instructor wording for definitions, purpose statements, architecture roles, and interpretive claims likely to be graded by phrasing.
- Use textbooks as clarification and gap-filling unless the user requests a full reading summary.

## Summary Documents

When generating a study summary from an outline:

- Follow the outline structure.
- Preserve source order.
- Include section numbers, slide ranges, page ranges, or reading references when available.
- Convert outline bullets into dense but readable study notes.
- Keep key ideas, mental pictures, why-this-matters notes, definitions, common confusions, exam traps, and quick triggers.
- Make the summary suitable for later compression into a cumulative exam review.

## Coverage Audits

Compare each completed outline or summary against the original slides, readings, notes, diagrams, and instructor examples. Record gaps in `Study/LectureN-coverage-audit.md`, then correct the Markdown outline before regenerating derived artifacts.

Check explicitly for:

- Omitted definitions
- `Purpose of` statements
- True/false-ready claims
- Architecture component roles
- Instructor-specific wording
- Diagram-only claims
- Named stages, percentages, sequences, and taxonomy distinctions
- Interpretive claims emphasized by the instructor

Do not treat conceptual coherence as proof of complete coverage. Include simple, easily overlooked claims as well as difficult concepts.

## Quick Recall Sheets

Generate `Study/LectureN-quick-recall.md` from the audited outline. For each item, write:

- One short question or trigger
- One-line canonical answer

Preserve instructor terminology. Cover simple definitions and purpose statements as well as difficult concepts. Do not turn the quick-recall file into another narrative summary.

Use about 30–60 prompts for a short lecture and 60–120 for a dense lecture, adjusting when the source scope warrants it.

Examples:

- `What is the purpose of an autoencoder? → Compress and reconstruct data.`
- `Layer normalization normalizes across what? → All features within each sample.`
- `How may Transformer feed-forward layers be interpreted as storing memories? → As key-value pairs.`

## Retrieval Drills

Use `Study/LectureN-retrieval-quiz.md` for short batches of roughly 10–25 questions. Mix:

- True/false
- Single choice
- Multiple answer
- Fill in the blank
- One-line free recall

Require the learner to answer before revealing solutions. Grade each response as:

- Correct and immediate
- Correct but hesitant
- Correct after reasoning
- Incorrect
- Instructor wording mismatch

Treat hesitant or reasoning-dependent answers as retrieval weaknesses even when correct. Record misses and weak retrievals, then re-test them later with changed wording.

## Practice Quizzes And Exams

Match the instructor's demonstrated format, wording, and difficulty when known. Include both reasoning questions and retrieval questions, including deceptively simple definitions and purpose questions. Do not make every practice test harder than the real exam.

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

Model unequal point weights explicitly:

- Assign a point value to every question.
- Include some high-point-value simple questions.
- Preserve the instructor's weighting pattern when evidence is available.
- Do not let many low-value correct answers conceal a high-value retrieval weakness.

After grading, produce:

- Question accuracy
- Point-weighted score
- Missed concepts
- Correct answers
- Error classification
- Repair notes
- Suggested outline edits
- Suggested exam-sheet additions

## Point-Weighted Grading

Always report both:

- Question accuracy: `correct / total`
- Point-weighted score: `earned / available`

Do not infer readiness from question accuracy alone. Explicitly report when question accuracy and point-weighted score disagree.

## Error Classification And Repair

Classify each miss or weak answer in `Study/ExamErrorLog.md` before repairing it. Use:

- Conceptual gap
- Retrieval failure
- Instructor-phrasing gap
- Distinction failure
- Question-reading error
- Multiple-answer error
- Calculation or procedure error
- Ambiguity
- Guess

Record the source, question or trigger, point value, learner response, canonical answer, error type, selected repair, and re-test result when available.

Map error types to repairs:

| Error type | Repair |
| --- | --- |
| Conceptual gap | Add an explanation, diagram, comparison, or worked example. |
| Retrieval failure | Add quick-recall prompts and spaced retrieval. |
| Instructor-phrasing gap | Preserve and drill exact course wording. |
| Distinction failure | Add a paired contrast table and paired questions. |
| Question-reading error | Practice marking qualifiers. |
| Multiple-answer error | Justify each option individually. |
| Calculation or procedure error | Add worked practice. |
| Ambiguity | Record both interpretations and the expected course answer. |
| Guess | Return to active retrieval. |

## Repair Passes

When the user misses questions or identifies confusion:

- Classify the error before choosing a repair.
- Add a repair subsection to the relevant outline.
- Keep repairs near the original source topic.
- Mark high-yield repairs for later extraction.
- Update the quick-recall sheet and error log when the repair targets retrieval or wording.
- Re-test the weakness later with changed wording.
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

- Freeze lecture summaries before final practice unless there is a genuine error.
- Complete coverage audits for all in-scope material.
- Merge lecture quick-recall sheets.
- Run rapid retrieval drills.
- Administer point-weighted, professor-style practice exams.
- Repair only demonstrated weaknesses.
- Patch the allowed exam aid last.
- Merge midterm material with post-midterm material.
- Prioritize connections across the course.
- Preserve prior quiz repairs.
- Preserve prior midterm misses when they support later material.
- Mark concepts that recur across multiple lectures.
- Identify old material likely to reappear because it supports later topics.

## Readiness Criteria

Report readiness only when the learner:

- Can explain core concepts mechanistically
- Can recall canonical definitions quickly
- Can recognize instructor-specific terminology
- Can distinguish commonly confused concepts
- Can answer simple true/false and purpose questions reliably
- Has both high question accuracy and high point-weighted scores

Explicitly report when question accuracy and point-weighted score disagree, and identify the high-value weaknesses causing the difference.

## Interaction Pattern

When working with the user:

1. Ask what material is in scope.
2. Confirm the deadline, allowed exam aids, instructor format, and known point weighting.
3. Build or update outlines first.
4. Generate summaries and complete coverage audits.
5. Generate quick-recall sheets and move quickly to retrieval drills.
6. Administer point-weighted, professor-style practice assessments.
7. Report both grading measures and classify errors.
8. Repair only demonstrated weaknesses and re-test them.
9. Freeze source summaries before final practice unless there is a genuine error.
10. Patch the allowed exam sheet last, based on demonstrated misses.
