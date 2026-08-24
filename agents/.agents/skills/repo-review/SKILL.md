---
name: repo-review
description: "Compatibility entrypoint for complete mixed-surface repository review and review-and-fix requests. Delegate branch, PR, staged, release-readiness, whole-repository, fix-all, and review-and-fix work to review-graph so every applicable review skill, validation result, and final proof uses one orchestration contract. Use a focused skill directly for one narrow surface."
---

# Repo Review

Delegate complete mixed-surface repository review to
[`review-graph`](../review-graph/SKILL.md). This skill preserves the familiar
`$repo-review` entrypoint; it does not implement a second coordinator.

## Delegation

1. Read the complete `review-graph` skill.
2. Pass through the user's request, scope, authorization, base, exclusions,
   deadline, and isolation preference unchanged.
3. Follow the selected `review-graph` profile once and return its native final
   result without adding a second routing, validation, or synthesis pass.

Do not independently capture scope, inspect worker capacity, consult surface
routers, invoke `review-validator`, run surface orchestrators, or synthesize a
compatibility report. `review-graph` owns those actions and derives the
five-surface compatibility view from its final proof.

For a request confined to one narrow review contract, use the applicable
focused skill directly instead of this compatibility entrypoint.

## Behavioral Equivalence

A completed `$repo-review` must be observationally equivalent to successively
invoking every applicable leaf review skill against one captured source state,
then validating and synthesizing their accepted results. Parallel workers,
coalesced validators, exact evidence reuse, and coordinator fallback may change
execution order or location, but never coverage, findings, validation
attribution, or completion status.

Require the final `RepositoryReviewProof` produced and verified by the
`review-graph` runtime. Do not load its maintainer-facing evidence specification
unless diagnosing a verifier rejection. Do not claim completion from an
orchestrator table, routing ledger, worker plan, or conversation summary alone.
