# Rust Orchestrated Execution v1

Load once for the sequential Rust pass loop in one live context. Graph dispatch
keeps its own contracts. Selection and all domain checks remain unchanged.

## Parent Receipt

Record the live context ID, stable review scope, authorization, and captured
source fingerprint separately. The scope identifies the repository, base or
comparison, and reviewed paths. Authorization states which actions the user has
granted, including any fixes. Also record repository constraints, selected and
skipped skills with reasons, required references per pass, and the validation
ledger. Specialists inspect scoped source and nearby contract owners under this
parent receipt.

The complete selected `SKILL.md` plus applicable references is its execution
view. Domain checklists, finding standards, and conditional reference routing
remain mandatory. Load standalone discovery/report references only for direct
invocation without a parent receipt.

## Instruction Reuse

Use `scripts/instruction_receipt.py` with a private ledger in a temporary
directory. Run calls serially. Supply the complete ordered `SKILL.md` and
applicable references for each pass. This example runs from the dotfiles
checkout. For an installed copy, use the installed helper path with the
configured Python interpreter.

```sh
uv run --locked python agents/.agents/skills/rust-review-orchestrator/scripts/instruction_receipt.py \
  --ledger "$REVIEW_INSTRUCTION_LEDGER" --context review-session-1 \
  --scope REVIEW_SCOPE_ID --skill-id rust-parse-dont-validate \
  rust-parse-dont-validate/SKILL.md rust-parse-dont-validate/references/nonzero-numeric-refinements.md
```

Each call offers at most one UTF-8 chunk of up to 8,192 instruction bytes with
its file identity, byte offsets, and an `ACK` trailer. Once the entire response
is visible without elision, repeat the command with `--ack TOKEN` using the
token from the trailer. Check for elision even when the trailer is visible.
This advances to the next chunk or returns
`complete: true`. Begin the pass after receiving that completion receipt.
The ledger records each file as loaded after its final chunk is acknowledged.

If a response is interrupted or truncated, call again without `--ack` using the
same scope, context, pass, and paths. The helper resumes at the first
unacknowledged byte, including when the interrupted call acknowledged a previous
chunk. Use a smaller `--chunk-bytes` if needed and acknowledge the new offer.
Previously acknowledged text may be reused while it is still available in the live context.
After compaction or loss of that text, use a fresh context ID and reload.

Change the scope ID when the authorized review boundary changes. Resupply the
complete ordered paths when source inspection reveals another required reference.
A changed required file or selection invalidates the affected view. An in-scope
source repair keeps the scope ID and can reuse an unchanged instruction view.
Record instruction identity using the ordered view signature and its context and
scope IDs. Track source-read bytes separately from instruction bytes.

## Pass Result and Synthesis

Return one row with skill/group, instruction receipt identity, captured source
fingerprint, inspected file/line references, findings or explicit no-finding,
changes/read-only status, validator receipt IDs (reused/new/blocked), limitations
and handoffs. Preserve each lens's
required finding fields: contract, trigger, consequence, evidence, severity, fix.
A skipped/blocked pass is not a no-finding result.

The parent owns one final synthesis: selected/skipped passes, findings, fixes,
blockers, residual risks, loaded paths/digests, validation provenance, and final
production readiness. Do not repeat a standalone report for each pass.

## Validation Reuse

Match source/build fingerprints (including fixtures/dependencies), toolchain,
target, features, profile, instrumentation, exact test selection, and material
runtime configuration. Record command, result/exit, and artifact. Reuse only
matching successful evidence. After a repair, recapture source under the same
scope and check the prior findings and validators against the new source and
build identities before reuse. Reinspect affected findings and rerun affected
validators. Preserve failures and repairs with their original source identity.
Scientific arithmetic, tolerances, fixtures, RNG, or claims invalidate affected
scientific evidence.

Inspect required gates first; run only uncovered selections. Do not replay
named/package/workspace/CI tiers without a recorded policy, configuration change,
or deliberate repetition. Keep explicit skips, source references, and evidence
limitations through synthesis. [Fixture measurements](fixture.md) separate first
loads from rereads; bytes establish neither tokens, latency, nor review quality.
