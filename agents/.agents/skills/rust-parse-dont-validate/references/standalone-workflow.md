# Standalone Review Workflow

Read only for direct invocation without a parent scope and result contract.
Read [standalone discovery](../../rust-review-orchestrator/references/standalone-discovery.md),
then apply this skill's complete domain checklist.

## Scope Modes

Use changed-code mode by default. Inspect changed invariant-bearing types and nearby constructors, parsers, mutators, and consumers.

Use pull-request mode for a named PR, branch, or diff base. Prioritize new public boundaries, invalid stored states, discarded validation evidence, and missing rejection tests.

Use whole-repository baseline mode only when explicitly requested. Start with public construction, configuration, deserialization, setters, and repeated validation helpers; group findings by owning type.

## Handoff

Summarize boundaries and invariant owners reviewed, proof-bearing types, bypass paths closed, routed state/error/lifetime work, tests and validators, files changed, and confirmation that no git state mutation occurred when true.
