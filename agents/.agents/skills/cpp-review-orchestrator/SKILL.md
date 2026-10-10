---
name: cpp-review-orchestrator
description: "Coordinate C++ reviews spanning multiple contracts; use a focused skill for a single review concern."
---

# C++ Review Orchestrator

Coordinate focused C++ review skills without copying their content. Load selected skills in logical pass groups, record actionable issues, apply fixes only when the user requested them, validate the touched surface after each group, and finish with the existing broad production review as synthesis.

The intent is to replace a maintainer manually invoking several C++ reviews. Do not collapse build-portability, lifetime, invariant, parsing, exception, API-design, API-documentation, functional, scientific, concurrency, testing, and synthesis concerns into one blended pass and report it as orchestrated work.

## Ground Rules

Existing user authorization remains valid for the same operation and scope
across turns. A review is read-only; requested fixes include relevant local
edits and safe checks, but do not imply Git mutations or publication.

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user has explicitly authorized that operation and scope.
- Use read-only git commands to discover scope when needed.
- Default new C++ work to C++23, CMake presets, vcpkg, doctest/CTest, `just`, Semgrep, clang-format, and clang-tidy. Respect an established project stack; selecting this language skill does not require a repository profile or toolchain migration.
- Respect repository-local instructions and exact recipe/preset names plus documented compiler, standard-library, triplet, dependency, and sanitizer support.
- Prefer changed-file review by default. Use whole-repo baseline mode only when the user explicitly asks for a repository-wide or baseline audit.
- Outside graph-routing mode, honor any handed-off branch file list, diff, or
  baseline inventory.
- When the user asks to fix issues, implement actionable findings as each group discovers them unless the fix is blocked or unsafe.
- Select focused validators from touched risks. Do not run full CI by default.
- Maintain one cross-group validation ledger. Reuse still-valid results and record why focused red/green checks overlap a required final gate; repeated coverage is not independent evidence.

## Graph-Routing Mode

When `review-graph` requests a declarative handoff, read
[`review-graph/references/routing-handoff.md`](../review-graph/references/routing-handoff.md)
and return its records instead of running this skill's standalone grouped pass
loop. Return semantic decisions for every matched specialist, including justified
`not-applicable` decisions, and additions beyond path matches. The planner rejects
unassessed matches, expands unmatched omissions, and selects mandatory synthesis. Attach
applicable CDT++ references and exact validation requirements only to selected
records. Do not load specialist bodies, validate, synthesize, edit, create
subagents, or recursively invoke an orchestrator in graph-routing mode.

Otherwise read [standalone orchestration](references/standalone-orchestration.md)
for scope routing, applicable language guidance, pass receipts, and final synthesis.
