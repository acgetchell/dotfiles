# Published README and Rustdoc Navigation

- Prefer docs.rs destinations for API references and worked API examples. Detailed
  composition examples can live in crate/module docs or focused documentation-only
  guides, following the repository's existing structure. Keep a useful quickstart
  and capability summaries in README, with direct links to the detailed material.
- Keep repository-owned background and operational guides at their canonical
  destinations. If README is included with `include_str!`, inspect the rendered
  links: paths such as `docs/workflows.md` do not automatically point to GitHub from
  docs.rs. Use absolute repository URLs for the intended revision when needed.
- Use intra-doc links within Rust documentation where the target is available;
  use links that work on both GitHub and rustdoc in shared README content.
- Choose `latest` intentionally for current guidance and explicit versions for
  release-specific contracts. docs.rs builds crates published to crates.io; a merge
  alone does not publish new pages. Inspect locally generated destinations and
  anchors; a successful `cargo doc` build alone does not verify explicit URLs or
  current docs.rs availability. Do not publish or bump a version merely to make a
  documentation link live without maintainer authorization.
