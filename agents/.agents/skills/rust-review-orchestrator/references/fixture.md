# Sequential Rust Review Fixture

Run from the dotfiles checkout:

```sh
just rust-review-fixture
```

This reads the immutable issue #84 baseline
`fa7231d431db9d6207bed98be0e719d085a700bf` through `git show`; it never checks out
or changes Git state. Output goes to a fresh temporary directory. The baseline
must exist locally; supply another locally available revision as the recipe's
argument only for an intentionally different comparison.

## What Is Measured

`report.json` records the exact 14 selected skills from #84, seven explicit
skips, each body/reference path, SHA-256, byte length, loaded/reused status,
source fingerprint, compiler host/version, command, profile, feature set,
validation result, and deterministic downstream probe output. The original
selected bodies total 106,848 bytes; this excludes the parent and references.
`handoff.json` contains only source, selection, and initial validation evidence
for a blinded behavioral review; it omits the callback probe and its result.

The harness reads and writes the full selected instructions into `before/` and
`after/`. It includes the parent and routing reference, applicable tooling,
numeric-refinement and benchmark references, and the old tooling standalone reference
required by its unqualified direct-invocation rule. The new parent contract is
included only after the change. This is controlled execution of an explicit
reference selection, not an automatic trace of arbitrary agent behavior.

It measures a first pass and one deliberately unchanged revisit. Legacy loading
replays full bodies; execution-v1 reuses the receipt. Unique content is counted
by path and digest, and repeated emitted content is counted separately. Source
and probe bytes are separate inventory fields; repeated compiler or model source
reads are not measured. File hashing and executable helper code
are not counted as model instruction reads. No token, latency, or general review
quality inference follows from these bytes. The revisit is an explicit fixture
scenario, not a claim that every historical review reread every file.

## Source and Evidence

`scripts/fixtures/warmup/` is a reduced deterministic source fixture with four
Rust source/test/example files, a manifest/lock, command recipe, and docs. It
preserves the issue's specialist selection, not its original 15-file staged
snapshot. It deliberately does not implement adaptation, RNG, target density,
or Metropolis-Hastings; scientific review must respect that limited contract.

The source validation receipt establishes transition counts, state preservation,
and parsed bounds. Reuse those tests for unchanged source. The separate
`callback_probe.rs` uses a downstream proposal with a `Cell` counter: four
warmup cases invoke 100 discarded metadata callbacks for 100 transitions,
while the four ordinary bulk controls invoke zero. A regression test applies
the narrow correction to a temporary copy and proves all eight counts become
zero while the transition/boundary tests still pass. Do not "fix" the stored
counterexample; it is deliberate review input.

For a behavioral comparison, give independent reviewers the same source,
selection/skips, and initial transition-validation receipt, with either the
baseline or current instruction tree. Withhold callback expectations, probe,
measurement report, and the other reviewer's findings. Require source references,
new deterministic evidence, explicit no-finding rows, validation reuse, and one
final synthesis. Compare actual findings; a smaller instruction artifact alone
does not establish equivalent review quality.

For direct-invocation coverage, separately invoke a moved-report specialist
without a parent receipt and verify scope discovery plus its complete report.

## Live Receipt Helper

Use a temporary ledger unique to a live context, and supply the actual scope
fingerprint and all selected references for that pass:

```sh
uv run python agents/.agents/skills/rust-review-orchestrator/scripts/instruction_receipt.py \
  --ledger /tmp/rust-review-instructions.json --context review-session-1 \
  --scope SOURCE_FINGERPRINT --skill-id rust-trait-bounds \
  rust-trait-bounds/SKILL.md
```

The helper emits complete new content on stdout and the per-pass receipt on
stderr. Read all emitted content; if a tool truncates it, discard that context
receipt and reload with a new context ID. The helper never marks a review pass
complete and never decides whether validation evidence remains valid.

## Recorded Evaluation: September 26, 2026

With the reference selection above and unchanged semantic checklists:

| Emitted instruction bytes | Baseline | Execution v1 |
|---|---:|---:|
| Selected 14 bodies, first load | 106,848 | 104,941 |
| All bodies including parent, first load | 117,162 | 115,788 |
| References, first load | 28,336 | 29,140 |
| Total unique first load | 145,498 | 144,928 |
| Deliberately unchanged revisit | 145,498 | 0 |

The first-load reduction is only 570 bytes (0.39%). The larger modeled saving
requires an unchanged revisit with instructions still in context; it is not a
measured latency improvement. The nine source files contain 5,300 bytes; the
independent 100-transition probe contains another 1,188 bytes. Those inventory
figures exclude repeated source reads and generated reviewer probes.

The source identity was
`bf2293d0e05a293a820955c0f682bb56829c4a4dff9e6de1b27feefb1e6d9f3c`,
using Rust 1.98.1 on `aarch64-apple-darwin`, default features, test/debug profile.
All 14 domain checklist sections were compared with the immutable baseline and
were identical. The pass order, explicit routing, and seven skips were preserved.

Two independent, blinded reviewers completed all 14 passes on that same source.
Both found exactly one canonical P2: discarded warmup telemetry at
`src/adaptive.rs:24` and `:28`, with the unit-metadata test's coverage gap folded
into the same finding. Each independently ran a three-transition downstream
call/drop-counter probe: all four warmup cases produced three calls and drops,
and corresponding bulk controls produced zero. Both reused the supplied
transition tests and reported no separate scientific defect. Optional endpoint
and error-payload test strengthening was distinguished from a second defect.
The direct trait-bounds trial discovered scope and produced its complete
standalone report with a successful minimal-bound downstream consumer.

These live reviews establish detection on one reduced fixture, not broad review
quality equivalence. The candidate review also exercised receipt invalidation
when references were discovered and instructions received formatting/mode-wording
edits during the run: affected views reloaded and validation stayed reusable
because source was unchanged. Those extra reads and the separately read helper
are not the frozen byte replay in the table and provide no live cost reduction
claim. Future comparisons should freeze instructions and provide the complete
reference receipt before measuring live loading.
