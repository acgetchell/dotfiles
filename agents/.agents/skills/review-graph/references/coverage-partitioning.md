# Partitioning Audit Coverage

Use this procedure for a broad fresh audit or a repair that repeatedly invalidates
unrelated capability contracts. `coverage_units` partition an audit's work;
they do not create more workers or change its routed ownership.

## Choose Contract Boundaries

Partition by language/activity and the contract being judged. For example,
notebook execution, scientific calculations, parser diagnostics, and operational
output can have separate dependencies even within one specialist's audit.
Group implementation, tests, and callers together when a judgment needs them.
A single parser unit spanning every input adapter is usually too broad when
the adapters have independently specified contracts; separate the adapters and
declare their shared parser dependencies explicitly.

Choose these boundaries from inspected behavior and caller contracts. Path
matches suggest candidates; a filename, directory, repository identity, or
project profile does not prove semantic independence. Keep every applicable
review, owned path, finding, and unresolved coverage item accounted for.

For each unit:

- Assign its `owned_paths` and one-based `finding_indices` exactly once across
  the complete partition. An owned file cannot be split among units.
- Put the concrete contract files and shared implementation it depends on in
  `dependency_paths`. A dependency may appear in several units. Account for
  every inspected `nearby_contract_owners` path somewhere in the partition;
  include it in every unit whose judgment actually depends on it.
- Include shared manifests and applicable instructions as whole files wherever
  they affect the judgment. Partitioning does not exempt environment, source,
  instruction, routing, validation-identity, or Git-sensitive proof gates.
- Leave `dependency_uncertainty` empty only when the dependency boundary is
  understood. Record a unit-specific unresolved relationship there; keep
  audit-wide uncertainty and omitted coverage in their existing typed fields.

Scientific units retain independent oracles and relevant numerical/model
assumptions. Partitioning cannot turn implementation agreement into independent
validation. Scholarly authorship boundaries also continue to apply.

## Broad Documentation Dependencies

Prefer independently owned capability contract files when their semantics can
be separated. For example:

| Unit | Owned implementation | Contract dependency |
| --- | --- | --- |
| Notebook execution | `notebook.py` | `docs/contracts/notebook.md` |
| Scientific calculations | `scientific.py` | `docs/contracts/scientific.md` |
| Operational diagnostics | `tool.py` | `docs/api.md` |

Here `docs/api.md` links to the first two contracts and owns only operational
diagnostics. An operational-doc edit can preserve the first two units. A change
to `docs/contracts/notebook.md` must invalidate the notebook unit. If the API
document also defines shared support policy or assumptions used by a capability,
that capability must retain the API document as a dependency.

These are illustrative contract roles, not required paths. Splitting a document
is source work requiring repair authorization. Preserve its meaning, links,
and ownership; capture and review the split before it becomes a fresh partition
origin. Do not retrofit narrower dependencies into sealed reports. In a
repository without independent contract files, keep the broad file dependency
and accept conservative rechecks.

### Section-Level Dependencies

The current runtime proves complete path identities, including file type and
mode. `dependency_paths` accepts paths, not Markdown anchors, line ranges, or
caller-authored section digests. Reading one section does not narrow the file
proof. This whole-file approach avoids treating a moved, deleted, renamed, or
duplicate section as an unchanged contract.

Section-level support would require a separate, versioned proof: independently
retained full-file bytes bound to both captures, unambiguous structural parsing,
and verification of the selected content plus its enclosing context and
position. Relevant edits, moved/deleted/ambiguous sections, changed ancestor
contracts, type/mode changes, and uncertainty would invalidate safely. Manifests
and instructions would still require whole-file proofs. Until those guarantees
are implemented, use capability-specific files or the conservative broad file.

## Verify Repairs And Report Effects

Inspect `coverage_reuse_decisions` for per-unit dispositions, reasons, and
dependencies. Its `input_changes` lists changed owned and dependency paths
from complete content/type/mode identities, including additions and deletions.
It is explanatory reporting; the immutable proof retains its original verified
decisions. Empty path lists do not imply eligibility: uncertainty, instructions,
boundaries, and metadata can still require a recheck.
An unrelated operational repair should preserve unaffected
capability evidence; a relevant contract repair should recheck its consumers.
Inspect only the recheck units and reconcile inherited validation requirements
and handoffs. The compiler preserves reused findings with their original
evidence IDs and retains historical findings in the immutable proof.

The [contract-partition fixture](dispatch-overhead.md#capability-contract-partitions-147)
compares broad and capability-specific dependencies on identical source bytes.
It also exercises relevant edits, shared manifests, instructions, and uncertain
dependencies through publication, compilation, and evidence verification.

Report rechecked paths, materialized dispatches, publication/compilation calls,
worker-input bytes, and proof bytes separately. Partitioning can reduce source
reads without reducing worker launches, and proof transport can increase input
bytes. Scripted fixtures do not measure model judgment, launch latency, token
usage, or provider cost. Leave unavailable provider measurements unknown;
neither fewer paths nor fewer nodes proves a cost saving.
