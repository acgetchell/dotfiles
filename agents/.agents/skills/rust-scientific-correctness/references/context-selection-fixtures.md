# Scientific Background Selection Trials

Use these fixtures when changing scientific background-selection instructions,
not during ordinary crate review. The synthetic `markov-chain-monte-carlo`
repository is in [`scripts/fixtures/mcmc`](../scripts/fixtures/mcmc/AGENTS.md).
It contains isolated rank, proposal, and checkpoint changes, plus a coupled
checkpoint/proposal-state case and their contracts.

For each case, give a fresh reviewer only the skill, the matching crate reference,
the fixture repository location, and the named changed source. Ask for a read-only
scientific review, concrete independent evidence, and a record of the context
actually loaded. Keep this procedure and its expected outcomes out of the review
input. Do not supply other reviewers' results or tell the reviewer which defect
to find. The parent supplies scope and a simple findings/read-log result contract;
standalone scope discovery and graph orchestration are unnecessary.

| Changed source | Required background beyond `AGENTS.md` and relevant scientific basis | Context not required without a discovered dependency | Retained finding and independent evidence |
| --- | --- | --- | --- |
| `src/ranks.rs` | `docs/DIAGNOSTICS.md` | Proposal validation, checkpoints, adaptation, RNG reproducibility | Tied observations receive the lowest rank rather than the average: pooled `[1, 2, 2, 4]` must give `[1, 2.5, 2.5, 4]`. |
| `src/proposal.rs` | `docs/VALIDATING_PROPOSALS.md` | Diagnostics, checkpoints, adaptation, RNG reproducibility | Forward and reverse log probabilities are reversed. Equal target weights with forward probability `1/4` and reverse probability `1/2` must accept with probability `1`; the implementation gives `1/2`. |
| `src/checkpoint.rs` | `docs/CHECKPOINTS.md` and `docs/REPRODUCIBILITY.md` | Proposal validation, diagnostics, adaptation | Resume resets the generator to the original seed, violating exact continuation. Starting at seed `1`, two recurrence steps reach `13`; the next uninterrupted draw is `40`, but resume produces `4`. |
| `src/checkpoint_proposal.rs` | `docs/CHECKPOINTS.md`, `docs/REPRODUCIBILITY.md`, and dependency-driven expansion to `src/proposal_state.rs` and `docs/VALIDATING_PROPOSALS.md` | Diagnostics, adaptation | Resume resets a saved proposal parameter to its default. With saved `probability_one = 1/4`, uniform-target transition `0 -> 1` has forward probability `1/4`, reverse probability `3/4`, and acceptance `1`, giving transition probability `1/4`. The default parameter changes it to `1/2`, despite preserving RNG state. |

Also check the uncertainty rule: if a caller or shared helper couples one of
these contracts to another, the reviewer must load that background and explain
the dependency. The coupled checkpoint case exercises this branch: require an
explanation of how saved proposal state changes the transition kernel. The
table's exclusions are defaults, not permission to ignore
observed dependencies. Every case retains the full scientific checklist's
applicability assessment and an oracle independent of the implementation.

Measure bytes from actual reads: use `read_bytes()` (or the bytes for an exact
section read), record repository-relative path, byte count, and SHA-256, then emit
that content to the reviewer. Record repeated loads separately. Sum background,
source, and skill-instruction bytes separately; do not estimate them from the
intended path list, infer model tokens from bytes, or claim elapsed-time savings.
Report required context reached, justified expansions, unnecessary context, and
retained findings alongside those measurements. These small synthetic trials
provide behavioral evidence, not a claim about every real crate review.
