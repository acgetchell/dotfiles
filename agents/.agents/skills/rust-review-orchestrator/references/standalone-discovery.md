# Standalone Scope Discovery

Read repository instructions and honor the user's requested files or diff. With
no supplied scope, inspect `git status --short`, `git diff --stat`, and
`git diff --cached --stat`, then read the changed code and nearby contract owners.
For a named branch or PR use its actual base and head; do not silently substitute
unstaged changes. Review the whole repository only when explicitly requested.

Keep diagnosis read-only unless fixes are requested. Preserve compatibility and
unrelated work. Do not stage, commit, push, or otherwise mutate Git state without
explicit authorization. Use repository commands and the smallest evidence that
covers the risk. Report scope, source references, findings or explicit no-finding,
validation commands/results and limitations, changes, and remaining work, along
with the lens-specific report fields. Separate required fixes from optional work.
