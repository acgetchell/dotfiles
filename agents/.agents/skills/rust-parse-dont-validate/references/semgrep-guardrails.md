# Parse-Don't-Validate Static Guardrails

Load this reference only when a repository already uses Semgrep or a similar project-rule system and a recurring invalid-state regression has a low-noise syntactic signature.

Good targets include:

- public `*_unchecked` production APIs
- infallible raw-value ingestion for a known invariant-bearing type
- refined fields regressing to raw primitives
- public `validate_* -> Result<(), _>` APIs where callers discard proof
- direct deserialization of invariant-bearing domain state without a validated boundary

Keep rules repository-specific. Static matching cannot infer every semantic invariant.

For each rule:

- tie it to a documented recurring defect
- restrict paths and syntax enough to avoid generic Rust style policing
- add positive and negative fixtures
- allow deliberate internal/test escape hatches explicitly
- explain the preferred proof-bearing replacement in the diagnostic

Route rule syntax, harness integration, and workflow mechanics to `project-tooling-review`; this reference owns the semantic pattern being protected.
