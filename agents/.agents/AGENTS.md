# Shared Agent Instructions

## Branch Naming

When creating a branch, follow the repository's documented or established naming
convention. If no convention exists, use `<type>/<short-kebab-description>`, such
as `fix/validation-recovery` or `feat/review-routing`. Do not add agent or model
prefixes such as `codex/` unless explicitly requested. Choose the final branch
name before pushing or opening a pull request.

## Required Python Portability Skill

Always load and apply `$python-build-portability` before changing Python runtime
code, development scripts, tests or fixtures, packaging, or CI that executes
Python. This includes review fixes and changes in repositories that are not
themselves published Python packages. When Windows is supported, also read the
skill's `references/windows-boundaries.md` before editing.

Use the skill within the requested scope and repository validation policy;
loading it does not authorize Git mutations, unrelated changes, or a new CI
matrix. If the skill cannot be loaded, report that limitation instead of silently
substituting a generic review or claiming that portability was checked.
