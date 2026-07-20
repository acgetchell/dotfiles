# LaTeX And Publication Validation

Load this reference only when LaTeX, TeX tooling, publication builds, PDF generation, `chktex`, or TeX-produced documentation is in scope.

## Ownership Boundary

Keep this review mechanical: source structure, includes, labels, references, bibliography wiring, generated figures/tables, build reproducibility, and artifact freshness. Apply `academic-authorship-boundary` before editing substantive manuscript prose, captions that interpret results, or reviewer responses.

## Source And Build Checks

Check:

- one documented root document and intentional include order
- stable labels, references, bibliography keys, figure/table paths, and generated inputs
- no machine-specific absolute paths or undeclared local style files
- generated figures and tables come from named source workflows
- build commands isolate outputs from tracked sources when repository policy requires it
- warnings for undefined references, citations, duplicate labels, missing files, and overfull content are reviewed rather than buried
- reproducibility controls such as source dates, deterministic metadata, and stable asset ordering are honored when configured

Do not hand-edit generated tables, figures, bibliographies, PDFs, or derived TeX regions. Fix their owning source or generator and rebuild.

## Tool Discovery

Use repository commands and declared TeX distribution first. If a macOS recipe reports `chktex` or another TeX binary as missing, check the MacTeX path `/Library/TeX/texbin` before installing a second distribution. When the binary exists there, run the repository command with a narrowly extended `PATH` or configure the owning tool's external-tool path according to repository policy.

Do not treat an interactive-shell PATH as proof that CI, Doxygen, an editor, or a GUI launcher can find the same tools.

## Validation

Run the narrowest applicable sequence:

1. syntax/lint checks such as the repository `chktex` wrapper
2. bibliography and cross-reference build passes
3. the authoritative publication/PDF recipe
4. artifact freshness or reproducibility checks
5. visual PDF inspection when layout is part of the task

Record the TeX engine/distribution, resolved tool paths, root document, generated inputs, warnings, output artifact, and any unavailable fonts or external tools.
