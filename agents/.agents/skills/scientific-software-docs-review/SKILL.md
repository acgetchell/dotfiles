---
name: scientific-software-docs-review
description: "Review language-neutral scientific software documentation for mathematical and numerical claims, algorithms and invariants, validation methodology, limitations, benchmark interpretation, reproducibility, data and coordinate conventions, provenance handoffs, figures, generated research artifacts, and release-facing scientific consistency. Use for scientific C++, Rust, Python, mixed-language projects, and research software docs; add ecosystem-specific overlays only when their metadata is in scope."
---

# Scientific Software Documentation Review

Review the scientific layer that connects implementation, validation evidence, reproducibility, and public claims. Establish technical truth through the owning scientific-code reviewer before polishing language.

## Scope

Use changed scientific documentation by default. In release-readiness or whole-suite mode, inspect every active scientific topic, validation, benchmark, reproducibility, limitation, data-format, and research-artifact document supplied by the parent inventory.

## Ownership Boundaries

- Own scientific claim/evidence coupling, validation-method documentation, reproducibility, limitations, scientific data conventions, and generated research-artifact relationships here.
- Let `repository-docs-review` own general suite navigation, operational clarity, and generated-file workflow.
- Let language scientific-correctness reviewers own mathematical and numerical truth.
- Let `scientific-citation-audit` own bibliographic identity, DOI resolution, provenance validity, and credit.
- Let `scientific-crate-docs-review` own Rust/Cargo release metadata coupling.
- Let `academic-authorship-boundary` constrain manuscript prose and reviewer responses.
- Let project tooling own commands and generators.

Read [`references/cpp-projects.md`](references/cpp-projects.md) only when C++ project metadata, generated API sites, compiler support, CMake releases, or C++ package consumption materially affects the scientific documentation.

## Review Workflow

1. Inventory scientific algorithms, guarantees, validation reports, benchmarks, figures, datasets, and limitations in scope.
2. Identify the code, tests, data, scripts, notebooks, and release metadata that own each claim.
3. Map claims to current evidence and distinguish demonstrated results from goals or hypotheses.
4. Check conventions and reproducibility before presentation quality.
5. Defer bibliographic verification and manuscript prose to their focused boundaries.
6. Validate generated artifacts through their owning commands.

## Claims And Guarantees

Check that algorithm names, supported dimensions, input domains, invariants, topology, numerical guarantees, stochastic properties, and failure conditions match current implementation evidence.

Distinguish:

- mathematically guaranteed properties
- empirically validated behavior
- benchmark observations
- platform- or configuration-dependent behavior
- known limitations and unsupported cases
- planned or experimental capabilities

Flag absolute claims supported only by a narrow fixture, benchmark, or one platform. Avoid turning a test pass into a theorem or a benchmark win into a universal performance guarantee.

## Validation Methodology

Require enough detail to understand what the evidence measures:

- oracle or independent reference
- input generation and domain restrictions
- degenerate, adversarial, or boundary cases
- tolerances and numerical scale
- sample counts, seeds, repetitions, and statistical treatment
- supported configurations and excluded cases
- failure classification and acceptance criteria

Ensure validation code is independent enough to catch implementation errors. Route the correctness of the method itself to the relevant scientific-code skill.

## Reproducibility

Check that readers can identify the code revision, data source/version, configuration, dependencies, compiler/runtime, platform, random seeds, commands, and output locations needed to reproduce a result.

Separate lightweight verification from expensive experiments. State resource, service, dataset, and hardware requirements. Avoid machine-specific paths, undocumented ambient environment, wall-clock filenames, and mutable external data without version identity.

Review evidence before quoting it in findings or reports. Redact credentials,
tokens, personally identifiable information, private dataset identifiers, and
internal filesystem paths. Use safe summaries and placeholders that preserve
the reproducibility fact without disclosing private context.

## Scientific Data Conventions

Keep coordinate order, orientation, units, indexing base, dimension order, dtype, precision, missing values, endianness, schema version, and normalization consistent across code, docs, fixtures, notebooks, and external consumers.

Flag diagrams, tables, examples, or file snippets that silently use a different convention from the implementation. Treat data-format changes as compatibility changes when users or research artifacts consume them.

## Benchmarks And Performance Claims

Check workload definition, dataset provenance, scale, warmup, repetition, statistical summary, hardware/software environment, configuration, baseline identity, and measurement uncertainty.

Require claims to match the shown evidence. Avoid unqualified “faster,” “scales,” or “production-ready” language when results cover only one case. Keep benchmark methodology distinct from scientific validation unless the same experiment genuinely serves both roles.

## Figures, Tables, And Generated Artifacts

Trace each tracked figure, table, report, dataset summary, or publication artifact to its authoritative source and named regeneration workflow. Verify captions and surrounding documentation describe the current artifact, axes, units, legends, sample counts, and limitations.

Do not patch generated values or images manually. Fix source data, code, notebook, template, or generator and regenerate when authorized. Preserve source-owned results and report discrepancies when the authoritative change is outside scope.

When documentation and manuscripts share an artifact, prefer one canonical source with explicit consumers. Route interpretive manuscript prose and polished captions through the academic authorship boundary.

## Release Consistency

Check that release-facing scientific feature, validation, limitation, and compatibility statements agree across the README, topic docs, migration guidance, generated reports, and package metadata. Route ecosystem-specific version/authorship/license coupling to the appropriate overlay.

## Output

Lead with unsupported or misleading scientific claims. Report authorities inspected, claim/evidence mismatches, convention and reproducibility gaps, generated artifacts deferred or refreshed, ecosystem and citation handoffs, validators run, and unavailable evidence.
