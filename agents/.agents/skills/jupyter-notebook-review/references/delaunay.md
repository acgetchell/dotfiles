# delaunay Notebook Review Notes

Use this reference when applying `jupyter-notebook-review` to the `delaunay`
repository. Read `AGENTS.md`, `docs/dev/notebooks.md`, `docs/dev/commands.md`,
and `docs/dev/docs.md` first; repository guidance overrides stale details here.

## Cell Identity

- Require every code, markdown, and raw cell to have a unique lowercase
  kebab-case ID of at most 64 characters.
- Preserve descriptive IDs when editing cells. Reject generated hexadecimal or
  UUID identifiers and positional names such as `cell-1`.
- Use `just notebook-check` as the authoritative repository validator. The
  structured checker owns presence, shape, length, and uniqueness; Semgrep adds
  qualitative guards for generated and positional names.

## Execution

- Keep routine validation lint-only with `just notebook-lint` or
  `just notebook-check`.
- Execute one notebook deliberately with `just notebook-execute <path>` only
  when runtime behavior or its artifact is in scope.
- Do not add an execute-all recipe or a permanent `slow/` notebook directory.
  Runtime depends on user-controlled parameters.

## Artifact Ownership

- Ordinary execution writes under `target/notebooks/<notebook-stem>/` and must
  not modify source notebooks.
- Refresh tracked figures only through their named recipes:
  `just spherical-readme-hero`, `just validation-doc-figures`, or
  `just paper-figures`.
- Keep canonical tracked figures under `docs/assets/`. Documentation and papers
  should reuse the same asset instead of maintaining paper-local copies.
- Default notebook save paths to scratch output. Let named recipes provide
  tracked destinations through validated environment overrides; do not call
  `savefig` or `write_image` directly on `docs/assets/` or `docs/images/` paths.

## Handoff Validation

- Run `just notebook-check` for notebook source changes.
- Run the named refresh recipe only when the requested change includes the
  tracked artifact, then verify its documentation and paper consumers.
- When notebook checker Python changes, also run the focused Python checks and
  tests selected by `docs/dev/commands.md`.
