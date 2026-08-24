---
name: review-validator
description: "Plan and execute repository validation against a captured source state, either standalone or from an exact review-graph dispatch. Return reproducible fingerprinted validation evidence without reviewing code, diagnosing findings, applying fixes, or broadening scope."
---

# Review Validator

Produce validation evidence, never review findings or fixes. Select the mode
before loading references:

- For a `review-graph` dispatch, read only
  [references/graph-dispatch.md](references/graph-dispatch.md) and return its
  compact `ValidationPayload`. The graph compiler creates and verifies the
  native artifact and evidence envelope.
- For a direct request, read
  [references/standalone-workflow.md](references/standalone-workflow.md) and
  [references/result-contract.md](references/result-contract.md), then plan,
  execute, reconcile, and return the complete standalone result.

## Graph-Dispatched Mode

Use graph mode whenever the request names `review-graph`, even if the dispatch
is incomplete. Require the exact coalesced `ValidationUnit`, captured source
identity, execution location, fresh-context identity, state-verification
command, commands, working directories, environment, toolchain, features,
platform, artifact policy, dependency policy, and elapsed bounds. Return
`blocked` for an omission; never fall through to standalone discovery.

Require the graph-owned effects, isolation, artifact-provenance, and snapshot
policy. Capture relevant filesystem and Git state before and after; return both
snapshots beside, not inside, the compact payload for compiler audit.

Honor executor placement. A worker uses `fork_turns: "none"`; a coordinator
fallback executes the same unit locally. Do not create another worker, split a
coalesced unit, re-plan, broaden commands, or inspect implementation semantics.

Run the exact state check before and after the unit. Independently reject a
dispatched command if its repository-owned definition is source- or
Git-mutating. Execute each command once in its declared order, honoring the
dependency policy. Record exact command, working directory, executor, result,
exit code, elapsed time, concise output evidence, and approved artifact paths.

Return only the compact payload. The graph owns evidence identities, command
and environment digests, mappings, canonical artifact compilation, acceptance,
reuse, invalidation, and final reporting.

## Universal Boundaries

- Do not load review skills, search for defects, assign severity, diagnose
  failed evidence, synthesize findings, recommend fixes, or edit source files.
- Create only approved ignored/external artifacts. Run source-mutating backends
  only in the dispatched isolated tree; never mutate Git state.
- Do not install substitute toolchains, alter dependencies, or change
  configuration to make a command pass.
- Reuse evidence only when source, command, environment, configuration,
  selection, and artifact identity match exactly.
- A failed command is validation evidence, not automatically a product finding.

## Status

Use `blocked` when execution could not proceed safely or source identity was
lost; `failed` when an executed command failed; `passed` when all requirements
are satisfied and at least one command ran; `reused` only when all requirements
were exactly satisfied without execution; and `not-applicable` only for a
zero-requirement, zero-command plan.
