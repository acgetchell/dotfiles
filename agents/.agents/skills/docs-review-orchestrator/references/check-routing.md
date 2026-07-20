# Documentation Review Routing

Use this matrix after establishing scope. Select skills individually and validators separately.

## Scope Discovery

Default to branch scope, including committed branch changes and staged, unstaged, and untracked work. Use staged-only, changed-file-only, release-readiness, or whole-repository scope when requested or handed off by `repo-review`. A named release patch, diff, or file set remains changed-scope; only an explicit release-readiness or release documentation audit expands to the active release suite.

In release-readiness or whole-suite mode, inventory every tracked active document. Classify generated, template, archived, or excluded files. A diff supplies change context but does not bound a full documentation-suite review.

## Individual Skill Routing

| Skill | Select when | Skip when |
|---|---|---|
| `repository-docs-review` | Active repository docs, navigation, operations, architecture, policies, release/migration guidance, generated-doc ownership, or cross-document consistency | Source-comment-only API docs with no suite effect |
| `scientific-software-docs-review` | Scientific claims, algorithms, validation, numerical limitations, benchmarks, reproducibility, data conventions, figures, or research artifacts | Repository is scientific but scoped docs contain no scientific claim/evidence surface |
| `scientific-crate-docs-review` | Scientific Rust Cargo/README/CITATION release coupling, crate identity, or generated changelog metadata | Generic scientific Rust docs without crate release metadata |
| `cpp-api-docs` | C++ public comments, Doxygen/generated reference, headers/modules, caller contracts, or canonical examples | Docs merely mention C++ behavior already established elsewhere |
| `rust-api-docs` | Rust `///`/`//!`, public coverage, structured sections, intra-doc links, docs.rs | Rust behavior is mentioned only in downstream prose |
| `scientific-citation-audit` | DOI/source identity, bibliography, algorithm provenance, scientific credit or citation claims | Ordinary links or CFF version/date-only synchronization |
| `academic-authorship-boundary` | Substantive manuscript prose, publication text, thesis/Praxis content, or reviewer responses | Mechanical publication tooling, labels, figure paths, or bibliography wiring only |

## Shared Ownership

- Commands: project tooling owns truth; repository docs owns clarity and placement.
- Code/API behavior: language reviewers own truth; docs specialists own rendered contracts and downstream consistency.
- Scientific claims: scientific-code reviewers own validity; scientific software docs owns claim/evidence presentation.
- Scientific Rust release: scientific software docs owns claims; crate docs owns Cargo/release coupling.
- README: repository docs owns repository role; add scientific, API, crate, or citation skills only for matching content.
- `CITATION.cff`: crate overlay owns Rust release synchronization; scientific software docs owns non-Rust scientific release synchronization, using a language reference when applicable; citation audit owns bibliographic/provenance validity. Version/date-only synchronization does not trigger citation audit.
- Generated API links: repository docs owns an ordinary README or navigation link; select the language API-doc skill when comments, generator configuration, public coverage, rendered reference content, or canonical API examples are evaluated.
- Papers: academic boundary governs prose; other skills may own mechanical build, references, figures, and artifact freshness.
- Generated docs: fix the source or generator and regenerate when its authority is in scope; never patch derived output to hide drift.

## Common Combinations

- Generic README/runbook: repository docs only.
- C++ Doxygen comments: C++ API docs; add repository docs only when guides/navigation also change.
- Scientific C++ release docs: repository docs plus scientific software docs; add C++ API docs for public reference claims.
- Scientific Rust release metadata: repository docs plus crate docs; add scientific software docs only when scientific claims or evidence change, and add Rust API docs or citations only when independently triggered.
- Bibliography-only audit: citation audit; add academic boundary only if manuscript prose would be edited.
- Paper artifact refresh without prose edits: repository/scientific docs as applicable; academic boundary may be skipped with the mechanical scope recorded.

## Validation

Use repository commands first. Match evidence to the surface:

- docs/site build for navigation and rendering
- generated-output drift checks for source-backed docs
- Markdown, link, spelling, and configuration checks
- Doxygen and compiled examples for C++ API docs
- rustdoc, doctests, and docs.rs configuration for Rust API docs
- CFF and DOI metadata checks for citations/release metadata
- publication build and artifact freshness checks for papers

Language or tooling validators establish quoted behavior and commands; they do not replace documentation rendering checks. Report network-, installation-, compiler-, or generator-bound gaps.

## Handoff Evidence

Report selected and meaningfully skipped skills, scope per skill, references loaded, authorities inspected, findings/fixes, validators, generated artifacts, unavailable evidence, and git-state status. Add a compact truth-owner record for external language, scientific-correctness, build, or tooling evidence actually consulted. Keep evidence attributable to individual skills.
