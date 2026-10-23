# Typed Review Results And Recovery

Apply this contract to review work, including direct skill invocations. A valid
negative judgment requires the expected inspection evidence. Missing input,
missing evidence, stale captures and malformed output remain unknown or blocked;
never substitute empty arrays, `false`, `not-applicable`, `no-findings` or `passed`
to make an incomplete result parse. An empty array is valid only when the
required inspection actually established no items.

Graph workers use their dispatched payload schema. Required fields are checked
before semantic compilation; JSON rejects duplicate keys and nonfinite numbers.
The compiler checks scope, dependencies, source identities and substantive
requirements before accepting evidence. Schema acceptance alone establishes
neither correctness nor successful execution. Valid findings and failed checks
are results to preserve, not malformed responses to retry away.

Runtime diagnostics include a typed `rejection` with `accepted: false`, a stable
`kind`, and one `recovery` action scoped to `affected-evaluation`. The
[wire schema](schemas/review-outcome-v1.schema.json) closes these variants and
the executable `next-ready` action. Existing approval and isolation receipts
retain their specialized contracts.

| Rejection kind | Required action |
| --- | --- |
| `missing-required-input` | `supply-required-input` from actual evidence |
| `malformed-input` | `correct-input`, preserving truthful findings |
| `missing-evidence` | `obtain-evidence` or retain the blocker |
| `stale-capture` | `recapture-source` and invalidate affected work |
| `unsupported-transition` | `reconcile-transition` through a supported operation |
| `unclassified-failure` | `inspect-blocker`; do not guess a retry policy |

`automatic_retry` is always false. Complete the prerequisite before requesting
another attempt. Honor the existing operation's attempt limit, run control,
repair budget and permission boundary; a typed action grants no new authority.
Schema correction permits the existing single diagnostic-guided retry. A second
failure stays blocked. Do not repeat unchanged requests, rerun successful
validators for metadata corrections, or restart comprehensive review solely for
rejected bookkeeping. Keep original failures and immutable evidence.

For direct invocation without a graph, retain the skill's normal user-facing
format. Name missing evidence and report the affected conclusion as blocked;
do not invent dispatches or evidence IDs. If producing machine-readable results,
parse the declared tagged variants before consumption and reject unknown or
incomplete variants. In Python use frozen domain objects or discriminated unions
after transport parsing; never treat annotations or unchecked casts as proof.
