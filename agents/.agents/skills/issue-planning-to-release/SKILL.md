---
name: issue-planning-to-release
description: "Plan issues into reviewable PR groups and bounded releases with explicit publication and downstream adoption dependencies."
---

# Issue Planning to Release

Turn issue acceptance criteria and downstream needs into a plan that delivers
usable published capabilities. This skill owns shared scope, sequencing,
publication-boundary, and validation-ownership policy. Use
[github-issue-planning](../github-issue-planning/SKILL.md) for native metadata
mechanics and [rust-ecosystem-release-train](../rust-ecosystem-release-train/SKILL.md)
for Rust-specific release coordination. Leave executable release procedures in
the owning repository's guides.

## Establish Current Evidence

Identify the requested repositories, outcomes, and release scope. Inspect relevant
issues and acceptance criteria, current native blockers, milestones, linked PRs,
manifests/locks, registry versions, release and validation guides, working adapters,
and consumer adoption needs. Follow dependencies far enough to establish the
publication boundary; do not expand into an ecosystem-wide audit by default.

Prefer current native metadata and repository contracts over stale issue prose.
Distinguish recorded blockers from proposed technical dependencies and report
conflicts. Paginate relevant lists; inaccessible or partial results are unknown,
not proof that a tracker, release, or blocker is absent. Record source links and
revision/retrieval context for consequential decisions. Do not hard-code current
versions, issue groupings, or repository names into reusable policy.

## Keep Ownership and Availability Explicit

Use this dependency direction:

```text
shared implementation issue -> upstream validation and registry publication
                           -> separate consumer adoption issue and verification
```

A consumer's missing shared capability belongs in its supplier's implementation
issue, linked to a separate consumer adoption issue. Implement and validate the
shared capability in its owning repository, including small representative
installed-package fixtures. An upstream release must not depend on completing
real consumer changes, CI, or publication. Its linked adoption issues may remain
open after it is complete.

Track these states separately, with their owning repository and evidence:

| State | Required distinction |
| --- | --- |
| Implemented | Acceptance evidence for the supported capability, including any remaining scope |
| Merged | Actual merged revision; an open or green PR is not merged |
| Published | Exact supplying version verified on PyPI/crates.io and normally resolvable; a tag or GitHub Release alone is insufficient |
| Pinned | Consumer manifest and normal lock resolution use that published version |
| Verified | Consumer integration and its required domain/native checks pass for the adoption revision |

Normal adoption uses published PyPI/crates.io dependencies, never editable
installs, sibling checkouts, Git/path overrides, or private helpers. Upstream
wheel/sdist or crate fixtures before publication prove the supported package
contract; they do not establish registry availability or actual consumer adoption.
Preserve working consumer adapters until the published replacement is verified.

## Choose PR Groups and Publication Cutoffs

Group by shared contract and downstream outcome. Combine work when that reduces
repeated implementation, review, publication, or adoption costs while preserving
reviewability and rollback boundaries. Keep security/trust-policy changes
independently reviewable and preserve scientific correctness. Neither one PR or
release per issue nor one comprehensive release is the default.

For every proposed release, specify:

- **Mandatory scope:** exact issues and acceptance needed for the useful outcome.
- **Supporting partial work:** the required slice of a broader issue, its public
  contract, and the acceptance still outstanding. A supporting slice must itself
  be coherent and safe to ship.
- **Deferred scope:** exact issues or residual portions, reasons, and later owners;
  say explicitly when nothing is deferred.
- **Publication cutoff:** publish once the bounded scope and required upstream
  gates are satisfied; name what will not hold it open. Use a date only when
  supported by an actual deadline or estimate.

Compare useful delivery time against the savings from batching. Count design,
implementation, independent review, upstream validation and publication, and
later consumer pin/lock, integration, and CI costs. Distinguish elapsed critical
path from aggregate runner time; parallel jobs do not add directly to elapsed
time. Label measured, reported, estimated, and unknown costs. Do not invent
timings, percentages, or speedups; an hours-long CI report is motivation, not a
measured saving.

Prioritizing implementation without an earlier publication boundary does not
deliver earlier downstream benefit. Split independent work when it materially
delays useful publication; batch related work when common validation/adoption
overhead outweighs that delay. Honor an explicitly chosen comprehensive release:
present a reasoned scope-change proposal when warranted, never silently replace
the agreed scope or move its milestone items.

If a small prerequisite becomes an unresolved architectural redesign, insert an
issue-mapped decision checkpoint before it absorbs the release. State the question,
bounded investigation/evidence, and choices: retain the dependency with a revised
scope, ship an independently useful subset, or defer the blocked capability while
retaining the existing safe behavior. Do not call rollback or failure handling a
successful implementation of the original requirement.

## Map Every Plan Item

Every numbered step, PR group, release/publication stage, decision checkpoint,
and consumer-adoption stage must include its owning repository and exact issue
IDs/links. A compact table works well:

| Item / PR group | Owner and issue links | Contribution and completion boundary | Prerequisite / unlock | Validation and cost |
| --- | --- | --- | --- | --- |
| Descriptive stage or proposed PR | Repository plus linked issues | Completes, contributes to, or remains blocked | Required state, not merely issue order | Owning checks; known costs and uncertainty |

State whether each item completes an issue or only contributes to it. Audit broad
extraction/adoption acceptance before claiming closure. Publication requirements
remain outstanding after merge. Distinguish multiple phases of one PR or issue
from genuinely separate PRs; report planned PR count explicitly when useful.

Look for an existing release capstone and adoption trackers. If missing, identify
a **proposed, unfiled issue** with owner, concrete title, scope, dependencies, and
completion criteria. This explicit proposal can identify an otherwise untracked
stage; never invent an issue number or silently file it. A milestone alone does
not replace issue mapping. Do not describe a tracker as missing when access was
incomplete.

Show upstream release scope and later consumer follow-ups separately. Connect
consumer adoption to the supplying release's verified-publication state, not just
implementation closure. Independent consumer cleanup may proceed earlier under
its own issue; it does not justify dropping gates that still need the unpublished
capability. If an ecosystem capstone includes adoption, keep it distinct from each
upstream publication capstone so the dependency graph has no reverse adoption
blocker or artificial cycle.

## Assign Validation and Evidence

For each required guarantee, identify the owning validator and the source,
execution context, platform/feature, and artifact evidence it must establish.
Record results in the owning PR/CI records, not parallel fix/history logs.

- Shared tooling owns comprehensive generic regressions, public APIs, packaged
  resources, installed wheel/sdist or crate fixtures, and its required native
  platform checks.
- Consumers own focused published-package integration/wiring tests plus their
  domain, scientific, security, feature, and native guarantees. Those checks are
  separate adoption work, not prerequisites for upstream publication.
- Inventory duplicate scans, builds, validators, and reports before consolidating.
  Similar names or code paths do not establish equivalent coverage. Preserve
  findings gates and required reports as well as the checks producing them.

When planning CI reuse, artifact promotion, or validation deduplication, read
[validation evidence](references/validation-evidence.md). Follow each repository's
targeted iteration and required final-validation commands. Repeat satisfied checks
only for changed inputs/context, failures, unresolved concerns, or a required
approval-time gate. Never save time by weakening assertions, shrinking scientific
workloads, or treating skipped required coverage as success.

## Deliver Within Authorization

Planning is read-only by default. A plan does not authorize Git mutations, GitHub
metadata changes, registry publication, or work in separate consumer repositories.
Honor already-granted authorization for its action and scope; do not ask again.
When an additional action needs authorization, first make its exact proposed
changes and release/adoption boundary reviewable. Apply authorized metadata
changes through `github-issue-planning` and re-query the resulting state.

Conclude with the next executable item (or the exact decision blocking it), its
owner and issues, and which verified published release unlocks which consumer
issue. Distinguish planned states from achieved states and name missing evidence.

For maintenance and behavioral assessment of this skill, use
[behavioral evaluation](references/behavioral-evaluation.md); ordinary planning
does not need that reference.
