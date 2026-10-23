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
3. Follow its selected profile once; return its native result without another
   routing, validation, or synthesis pass.

Preserve its repair budget, delivery profile and stop reason. Routine delivery
reports fixes, affected verification and pending CI without claiming formal proof.

Do not repeat graph-owned capture, capacity, routing, validation, orchestration,
synthesis or five-surface compatibility reporting.

For one narrow contract, use its focused skill directly.

## Behavioral Equivalence

A completed `$repo-review` must be observationally equivalent to successively
invoking every applicable leaf review skill against one captured source state,
then validating and synthesizing their accepted results. Parallel workers,
coalesced validators, exact evidence reuse, and coordinator fallback may change
execution order or location, but never coverage, findings, validation
attribution, or completion status.

Default to routine delivery; use [certification](../review-graph/references/run-profiles.md)
only when requested. Certification requires the runtime's verified
`RepositoryReviewProof`, never tables, plans or conversation summaries. Load the
evidence specification only to diagnose verifier rejection.

Review outcomes: [typed contract](../review-graph/references/typed-results.md); read on rejection. Missing evidence stays blocked.
