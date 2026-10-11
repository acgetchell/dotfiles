---
name: repo-review
description: "Run a comprehensive repository review through review-graph; use a focused skill for a single contract."
---

# Repo Review

Delegate comprehensive repository review to
[`review-graph`](../review-graph/SKILL.md).

## Delegation

1. Read the complete `review-graph` skill.
2. Pass through the user's request, scope, authorization, base, exclusions,
   deadline, and isolation preference unchanged.
3. Follow the selected `review-graph` profile once and return its native final
   result without adding a second routing, validation, or synthesis pass.

Preserve its repair budget and stop reason; report unfinished proof as partial.

`review-graph` owns capture, capacity, routing, validators, orchestrators,
synthesis, and the five-surface compatibility view. Do not repeat those actions.

For one narrow contract, use its focused skill directly.

## Behavioral Equivalence

A completed `$repo-review` must be observationally equivalent to successively
invoking every applicable leaf review skill against one captured source state,
then validating and synthesizing their accepted results. Parallel workers,
coalesced validators, exact evidence reuse, and coordinator fallback may change
execution order or location, but never coverage, findings, validation
attribution, or completion status.

Require the runtime's verified `RepositoryReviewProof`; tables, plans, and
conversation summaries cannot establish completion. Load the evidence
specification only to diagnose verifier rejection.
