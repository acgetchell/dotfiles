# README Discovery and Published Navigation

- Keep README entry points easy to find: a copyable quickstart, brief capability
  descriptions, and direct links to fuller examples and contracts. Preserve useful
  detail in its canonical guide when shortening an overview; do not silently discard
  limitations or impose a fixed section layout or table size across repositories.
- Prefer the project's generated reference site for API documentation and worked
  API examples when that site supports them. Keep repository-owned development,
  operational, and scientific-background documents at their established repository
  or documentation-site destinations rather than duplicating the entire suite.
- When a README is also embedded in generated documentation or a package page,
  validate links and heading anchors in each actual rendering context. Relative
  repository paths can resolve against the wrong site base; use explicit URLs or
  the project's supported link transformation where needed.
- Check the intended version or revision of each destination and distinguish local
  rendering evidence from published availability. Route ecosystem-specific build,
  release, and API-link details to the relevant documentation specialist.
- Keep active README navigation independent of the package version: use the
  repository's default branch for current guides, source, and policies, and a
  stable alias such as docs.rs `latest` for published APIs. Check release updaters
  and their tests so the next release cannot restore version-dependent links.
  Verify destinations before tagging; rendering Markdown alone does not establish
  that linked pages exist. Retain immutable image and historical evidence links
  when their purpose requires provenance.
