# Standalone Python Review Orchestration

Read this reference completely only for a directly requested Python
orchestration outside `review-graph` routing mode.

## Ground Rules

- Prefer changed-file scope. Use whole-repository mode only when explicitly
  requested or supplied as a parent baseline scope.
- Honor a parent orchestrator's branch-scope file list instead of narrowing it
  to current worktree changes.
- When asked to fix issues, implement safe actionable fixes as each pass finds
  them.
- Use focused validators while iterating. Run full CI when explicitly requested
  by the user or required by repository policy or cross-layer risk.
- Maintain one cross-skill validation ledger keyed by source/environment state,
  built artifact and installation-target identity, Python/platform/dependency
  configuration, instrumentation, and exact test selection. Use a wheel,
  sdist, installed tree, or entry-point digest when applicable. Reuse
  still-valid evidence; record justified overlap when a required full gate
  repeats focused regression checks, without counting independent coverage twice.

## Establish Scope And Routing

1. Inspect the supplied scope. For a whole-package baseline, include unchanged
   package sources, metadata, tests, and the workflows that exercise them.
   For changed-file scope without a supplied inventory, use read-only git commands to enumerate
   the committed branch delta from its merge base, staged changes, unstaged
   changes, and untracked paths.
2. Read every untracked file completely with a file-appropriate reader before
   selecting skills; a status entry or filename is not evidence.
3. Use the [specialist routing table](check-routing.md#individual-skill-routing)
   to select and order passes for the scoped behavior.
4. State selected and not-selected skills with reasons before loading
   specialist bodies.
5. Load a repository-specific reference only when both the repository and its
   concern match.

Validator selection is independent from skill selection. Running tests for
changed code does not by itself require loading `python-test-quality`.

## Review Trace

For each selected skill, record why it applies, skill and reference files
loaded, changed files inspected, findings or an explicit no-finding outcome,
fixes, and focused validation or matching ledger evidence reused.

When a caller supplies an established scope, begin with a handoff receipt
naming the supplied scope and selected and not-selected skills, then provide
table-ready evidence. Name not-selected skills whose absence might otherwise
appear accidental.

## Per-Skill Fix Loop

For each selected specialist:

1. Announce the skill and why it applies.
2. Read its `SKILL.md` completely and only directly relevant references.
3. Inspect the changed surface and nearby contract owners.
4. Record findings or an explicit no-finding result.
5. Implement minimal fixes when authorized.
6. Run the smallest risk-covering validator only when equivalent evidence is
   not already valid in the shared ledger. Check a regression promptly before
   and after its fix even when a required final gate includes it.
7. Fix validator failures before continuing or document a genuine blocker.

After the fix loops, complete any required full gate on the final source state.
Follow [full CI routing](check-routing.md#escalate-to-full-ci) for requirements
known in advance or added after focused checks; overlap alone is not a blocker.

Do not claim orchestration from one undifferentiated pass. Preserve ownership
and evidence per selected skill.

## Final Summary

Lead with unresolved blockers. Include files changed, selected skills and
references, meaningful skips, fixes and reconciliations, the validation ledger
with any justified overlap, untested configurations or external limitations, and git
state. Return table-ready evidence when a parent requests it.
