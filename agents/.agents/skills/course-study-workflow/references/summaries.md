# Summaries and Coverage

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
