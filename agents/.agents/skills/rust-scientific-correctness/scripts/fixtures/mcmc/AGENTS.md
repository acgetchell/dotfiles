# Fixture Repository Guidance

This synthetic repository represents independent changes in
`markov-chain-monte-carlo`. Review only the assigned source and relevant contracts.
The scientific assumptions are in `docs/SCIENTIFIC_BASIS.md`. Domain documentation
is in `docs/`; no additional reviewer guidance is required. `src/ranks.rs`,
`src/proposal.rs`, and `src/checkpoint.rs` are self-contained, with no callers or
shared helpers outside those files. Follow declared module dependencies for
other assigned sources.

Keep this review read-only. Return findings with independent evidence, the
scientific dimensions considered, and the actual context-read record.
