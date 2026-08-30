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
is incomplete. Follow the compact graph-dispatch contract exactly; omissions
are `blocked` and never trigger standalone discovery.

Honor placement and the coalesced unit. Do not re-plan, split or broaden it,
create another worker, or inspect implementation semantics. The coordinator
owns before/after snapshots and all evidence identities and digests.

Write the recursive payload to the dispatched candidate path, publish it through
the runtime-owned `persist-worker-payload` operation, and return those bytes.

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
