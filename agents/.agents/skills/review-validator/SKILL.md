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

Graph mode requires an actual dispatch or explicit graph-unit request;
mentioning `review-graph` alone does not select it. Follow the compact contract:
an incomplete dispatch is `blocked`, never standalone discovery.

Honor placement and the coalesced unit. Do not re-plan, split or broaden it,
create another worker, or inspect implementation semantics. The coordinator
compiles evidence. The runtime owns snapshots and identities; invoke its
dispatched observation commands.

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

Review outcomes: [typed contract](../review-graph/references/typed-results.md); read on rejection. Missing evidence stays blocked.
