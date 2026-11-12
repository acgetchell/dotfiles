# Fictional Operational Planning Evidence

All repositories, issues, commands, versions, and observations below are fictional
test data. The inventories are complete; do not retrieve these identities from
GitHub or execute their commands. Commands describe fixture interfaces, not tools
installed in the evaluator's environment. All work is planning-only: no installs,
CI, benchmark acquisition, provider mutations, publication, or Git changes.

## Case E: Interrupted Scientific Release

`fixture-tools` supplies the PyPI package and CLI `fixture-evidence` to
`fixture-science`. `fixture-guidance` owns the release-planning skill and its
behavioral scenarios.

| Issue | Current scope and state |
| --- | --- |
| fixture-guidance#301 | Update release-planning instructions and behavioral scenarios for workflow usability; implementation pending |
| fixture-tools#201 | Installed CLI rejects the policy path used by draft preparation; unresolved |
| fixture-tools#202 | Repeated provenance walks in nested release commands; unresolved |
| fixture-tools#203 | Release setup installs the full contributor toolchain; unresolved |
| fixture-tools#204 | Interrupted asset batch has no documented continuation; unresolved |
| fixture-tools#210 | Filed release tracker for package 2.1: installed wheel/sdist command fixtures, required native checks, package verification and registry publication; pending |
| fixture-science#251 | Adopt the published tooling fixes through normal pins/locks and update workflow recipes and release guide; pending |
| fixture-science#260 | Filed product release tracker for v0.8.1: retained scientific/native evidence, asset completion, hosted operational acceptance, approval and publication; pending |

Registry version 2.0 is published and normally resolvable; it contains none of
#201–#204. Package 2.1 is neither implemented nor published. Product release
v0.8.1 targets protected revision S1; the tag already points to S1. The retained
acceptance selection is `retained/acceptance.json` with identity A1. All original
measurements, required native results, signed evidence and five asset digests are
valid for S1/A1 under the current policy. Those files are intact. Publication
still requires their verification and fresh approval-time checks. No evidence
equivalence across changed runtime/trust contexts has been approved.

The current release guide runs commands from the repository root. The workflow
uses the installed 2.0 package. Its command expansion is:

```text
just release-draft v0.8.1
  just contributor-setup
    install pinned package, linters, editor helpers and benchmark build tools
  fixture-evidence release prepare --version v0.8.1 --policy "$PWD/release-policy.toml" --acceptance retained/acceptance.json
    parse CLI arguments, audit provenance, create provider draft

just release-assets draft-84
  just contributor-setup
  fixture-evidence release audit --acceptance retained/acceptance.json
  fixture-evidence release verify --policy release-policy.toml --acceptance retained/acceptance.json
    release audit for the same A1 graph
  fixture-evidence release attach --draft draft-84 --policy release-policy.toml --acceptance retained/acceptance.json
    release verify, which calls release audit for the same A1 graph
    upload assets sequentially
```

The installed parser accepts only a repository-relative `--policy`. Draft
preparation exits during argument parsing for the absolute path above. A
maintainer later used the same prepare command with `--policy release-policy.toml`
on a warm workstation and obtained draft `draft-84`. The workflow does not yet
contain that correction. Library publisher unit tests and static YAML checks
pass; no installed-command fixture covers the absolute-path invocation.

Recorded observations from authorized previous attempts:

- Hosted asset job H1 on a cold Linux runner has a 30-minute timeout. It was
  cancelled while `contributor-setup` was still running, before verification.
  An isolated setup measurement H2 on the same runner image/tool revisions and
  cold cache completed in 34 minutes. No minimal release-tool setup timing exists.
- One warm audit trace for A1 visits eight provenance nodes, three provider
  requests per node. All three audits above traverse those same nodes; retries
  and unrelated calls are excluded from this trace. End-to-end hosted verification
  and upload durations have not been measured.
- A separate warm attempt H3 reached `attach`: it uploaded the first two assets
  to `draft-84`, saved their receipts, then lost its connection. No receipt exists
  for the third request, whose provider outcome is unknown. The remaining local
  files and A1 manifest are intact. Current `attach` fails when an asset name
  already exists; it has no documented resume behavior.
- A transport fixture can make draft creation succeed remotely and lose the
  response, but this case has not been exercised through the installed command.
  An approval-interruption fixture also has not been exercised. The protected
  publication job acquires credentials only after approval and fresh verification.

The following installed commands are documented in 2.0:

```text
fixture-evidence release inspect --version v0.8.1 --json
fixture-evidence release verify --policy release-policy.toml --acceptance retained/acceptance.json
```

`inspect` is read-only and reports draft IDs and asset names/digests. `verify`
does not mutate provider state; it reports invalid inputs without deleting them.
The guide says to correct an identified configuration error and rerun `verify`
against the retained selection. It does not document post-upload recovery,
ambiguous creation reconciliation, or re-entry after interrupted approval. There
is no `resume` subcommand. Safe transport fixtures can represent all these
provider responses without live publication. The installed CLI, recipes, and
hosted runner have not been exercised together after any proposed fix.

The maintainer requests a bounded delivery plan: what belongs in the skill,
shared tooling and consumer; what can be grouped; the real maintainer sequence,
costs and acceptance owners; and the next commands after each observed or
fixture-supported failure. Explain what is runnable now and what still needs
implementation or evidence before completing v0.8.1. Propose any extra gate with
its reason, owner and effect on maintainer work, latency and permissions.

## Case F: Conventional Release

`fixture-small#71` corrects a release-note typo; the documentation change and its
required checks are complete in an open PR. `fixture-small#72` is the filed release
tracker for v1.4.1. There is no shared-tooling change or consumer adoption work.
The existing guide and commands are unchanged:

```text
just release-check v1.4.1
just release-draft v1.4.1
just release-publish v1.4.1
```

Run from the repository root, `release-check` verifies the release revision and
retained package manifest; `release-draft` reconciles by version, verifies any
existing assets against that manifest and adds only missing assets; conflicting
digests stop it. `release-publish` resumes through the protected approval gate
and fresh verification before acquiring credentials. After a check failure, the
guide directs repair of the reported input and rerunning `release-check`. After
draft timeout or an ambiguous response, it directs rerunning `release-draft`;
after approval interruption, rerunning `release-publish`. Installed-command
transport fixtures cover successful retries, partial uploads and conflicts.

Three current authorized cold hosted runs for this unchanged path measured
2 minutes setup and 4–5 minutes verification/draft work within a 20-minute job
budget. Approval is outside that timed job; post-approval verification and publish
use a separate 10-minute job with observed 2-minute execution. Required checks
for the final release revision and registry verification remain pending in #72.
Those are existing release requirements. PR review and merge are also pending.
No additional acceptance gaps are reported in this complete inventory.

The maintainer requests the smallest sensible plan and next executable item.
State whether anything beyond the existing gates is needed and why. Execution
and publication remain unauthorized, as in Case E.

## Evaluation Request

Use the supplied skill and this evidence to write a plan for Cases E and F in the
supplied temporary directory. Include ownership, publication/adoption dependencies,
command and recovery paths, cost evidence, and remaining acceptance. Label
proposed command behavior separately from available behavior. Do not execute the
fixture commands or change any source repository or external record.
