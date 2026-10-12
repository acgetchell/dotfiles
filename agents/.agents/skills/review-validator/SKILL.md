---
name: review-validator
description: "Run repository checks and report source-bound validation evidence, either directly or from an explicit graph dispatch."
---

# Review Validator

Produce validation evidence, never review findings or fixes. Select the mode
before loading references:

- For a `review-graph` dispatch, start with
  [references/graph-dispatch.md](references/graph-dispatch.md) and return its
  compact `ValidationPayload`. The graph compiler creates and verifies the
  native artifact and evidence envelope.
- For a direct request, read
  [references/standalone-workflow.md](references/standalone-workflow.md) and
  [references/result-contract.md](references/result-contract.md), then plan,
  execute, reconcile, and return the complete standalone result.

## Graph-Dispatched Mode

Use graph mode for an actual graph dispatch or an explicit request to execute
a graph validation unit. Mentioning `review-graph` alone does not select this mode. Follow the compact contract exactly: an incomplete actual
dispatch is `blocked` and never falls back to standalone discovery.

Honor placement and the coalesced unit. Do not re-plan, split or broaden it,
create another worker, or inspect implementation semantics. The coordinator
owns before/after snapshots and all evidence identities and digests.

Stream the payload through the dispatch-bound publication command; return its
bound receipt. The runtime consumes persisted bytes. Skip candidate writes.

## Universal Boundaries

- Do not load review skills, search for defects, assign severity, diagnose
  failed evidence, synthesize findings, recommend fixes, or edit source files.
- Create only approved ignored/external artifacts. Run source-mutating backends
  only in the dispatched isolated tree; never mutate Git state.
- Do not install substitute toolchains, alter dependencies, or change
  configuration to make a command pass.
- Reuse evidence only when source, command, environment, configuration,
  selection, and artifact identity match exactly.
- Bind evidence to the actual executor; emulation never proves an unexecuted
  native matrix cell.
- A failed command is validation evidence, not automatically a product finding.

## Status

Graph-dispatched payloads allow only `passed`, `failed`, or `blocked`. Use
`blocked` for unsafe execution or lost source identity; `failed` for an executed
command failure; and `passed` when all requirements pass and a command ran.

Standalone results additionally allow `reused` for exactly satisfied requirements
without execution, and `not-applicable` for a zero-requirement, zero-command plan.
