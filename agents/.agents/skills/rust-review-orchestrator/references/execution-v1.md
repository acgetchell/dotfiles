# Rust Orchestrated Execution v1

Load once for the sequential Rust pass loop in one live context. Graph dispatch
keeps its own contracts. Selection and all domain checks remain unchanged.

## Parent Receipt

Record context/review ID, exact scope and source fingerprint, authorization,
repository constraints, selected/skipped skills with reasons, required references
per pass, and validation ledger. Establish missing fields once at the parent.
Specialists inspect scoped source and nearby contract owners using this receipt.

The complete selected `SKILL.md` plus applicable references is its execution
view. Domain checklists, finding standards, and conditional reference routing
remain mandatory. Load standalone discovery/report references only for direct
invocation without a parent receipt.

## Instruction Reuse

`scripts/instruction_receipt.py` emits complete new instruction text and records
canonical paths, SHA-256 digests, byte lengths, and scope/context IDs. Supply the
complete reference set per pass explicitly; it does not select references.
Update the receipt when source inspection reveals another required reference.

Reuse only unchanged instructions still available in the same live context,
with the same scope and required reference set. Changed content, scope, or
reference selection invalidates that pass's reuse. After compaction, a truncated
load, or lost context, use a new context ID and reload; a disk receipt alone
proves no model availability. Hashing is not instruction loading. Instruction
reuse proves neither source review nor validation. Keep source-read bytes
separate from instruction bytes.

## Pass Result and Synthesis

Return one row: skill/group, instruction receipt identity, inspected file/line
references, findings or explicit no-finding, changes/read-only status, validator
receipt IDs (reused/new/blocked), limitations and handoffs. Preserve each lens's
required finding fields: contract, trigger, consequence, evidence, severity, fix.
A skipped/blocked pass is not a no-finding result.

The parent owns one final synthesis: selected/skipped passes, findings, fixes,
blockers, residual risks, loaded paths/digests, validation provenance, and final
production readiness. Do not repeat a standalone report for each pass.

## Validation Reuse

Match source/build fingerprints (including fixtures/dependencies), toolchain,
target, features, profile, instrumentation, exact test selection, and material
runtime configuration. Record command, result/exit, and artifact. Reuse only
matching successful evidence; missing provenance or affected edits require
new validation. Preserve failures and repairs. Source edits invalidate affected
findings even if instructions are unchanged. Scientific arithmetic, tolerances,
fixtures, RNG, or claims invalidate affected scientific evidence.

Inspect required gates first; run only uncovered selections. Do not replay
named/package/workspace/CI tiers without a recorded policy, configuration change,
or deliberate repetition. Keep explicit skips, source references, and evidence
limitations through synthesis. [Fixture measurements](fixture.md) separate first
loads from rereads; bytes establish neither tokens, latency, nor review quality.
