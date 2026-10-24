# Fictional planning evidence

All repositories, issue IDs, measurements, and versions in this file are fictional
test data. Use these identities only as fixture references, never as GitHub URLs.
The inventories below are complete, including the absence of unlisted trackers.
No external retrieval is needed or authorized for these fictional repositories.

## Case A: dependency updates

`fixture-tools` supplies a PyPI package to `fixture-simulation`.

| Issue | State and acceptance |
| --- | --- |
| fixture-tools#11 | Preserve marker-specific package indexes when updating pins; implementation estimated ready tomorrow morning, review not yet done |
| fixture-tools#12 | Reject direct/transitive downgrades and recover the transaction; implementation estimated ready two hours after #11, review not yet done |
| fixture-tools#13 | Unrelated notebook editor integration estimated ready in three weeks |
| fixture-simulation#51 | Adopt #11 and #12 from a published version, remove both local workarounds, pass consumer native CI |

#11 and #12 use the same resolver boundary and installed wheel/sdist fixture
matrix. Their public interfaces are compatible. Either fix is independently
useful. No release capstone or milestone exists. Latest published package is 1.0;
it contains neither fix. The maintainer may choose the next compatible version.
No new release has been tagged, uploaded, or installed by the consumer.

Previous release records measure 50 minutes elapsed and 150 runner-minutes for
upstream native/package gates plus 15 minutes maintainer publication work. Each
consumer adoption cycle measures 35 minutes pin/wiring work followed by 3 hours
elapsed / 9 runner-hours native CI. Those are observed historical costs, not
guarantees of the next run. The consumer deadline is next week. Independent review
cost and queue time have not been measured. All three native platforms remain
required by the guides. Iteration uses `just check`; final upstream validation uses
`just ci` and installed wheel/sdist fixtures; consumer acceptance uses `just ci`
with numerical regression and slow-test buckets. Publication requires a fresh
registry install and public-interface smoke verification. Existing adapters work.

## Case B: merged extraction slice

`fixture-evidence` supplies a PyPI package to `fixture-geometry`.

| Issue | State and acceptance |
| --- | --- |
| fixture-evidence#30 | Broad extraction: evidence selection, signature verification, asset upload, templates and migration documentation; open |
| fixture-evidence#31 | Public evidence-selection command, installed wheel/sdist fixtures and migration notes, plus verified publication; code and generic fixtures merged at revision E1, publication outstanding |
| fixture-geometry#70 | Inventory redundant lint/report stages and assign ownership; no implementation yet; does not include evidence-command adoption |

#31 contributes the selection portion of #30. Signature and asset-upload portions
of #30 are not implemented; no estimate is available. Native upstream checks passed
at E1 but no release artifact has been promoted or published. Registry 1.0 lacks
the new command. There is no release capstone and no consumer adoption tracker.
The consumer keeps a working local evidence adapter and pins registry 1.0. Its
maintainer reports “full native CI takes hours”; no timing breakdown exists.
Upstream installed fixtures cover generic selection success and rejection cases.
Consumer verification must cover its real workflow configuration, scientific
inputs, platform matrix and approval handoff. The same authorization and release
guide boundaries as Case A apply. No consumer changes are prerequisites in the
upstream acceptance criteria.

## Case C: proposed evidence shortcut

`fixture-gates#41` requests cross-commit source-evidence reuse, initially described
as a small prerequisite for `fixture-gates#42`'s independently useful diagnostic
improvements. Inspection now shows that #41 needs an unsettled execution-context
and signer trust design. The maintainer has not chosen a policy or delivery date.
#42 can ship using the current exact-release-commit checks. No release tracker
exists; the next package version is undecided. Public CLI regressions and native
installed fixtures are required. No consumer adoption has been requested yet.

The associated `fixture-native#81` adoption request proposes skipping its main
matrix if PR and main trees match. The PR and protected-main commits P1 and M1
share tree T. Their workflows use different event/ref variables and credentials;
the windows result is missing. The retained PR Cargo archive embeds P1 in
`.cargo_vcs_info.json`; the release target is M1. There is no supported evidence
equivalence contract. Current policy requires all native platforms for the exact
release commit, retained release-artifact verification, and revalidation after
approval before credentials are acquired. A maintainer asks whether the shortcut
would allow the release to finish sooner, but has not authorized gate changes.

## Request

Use the supplied skill to produce a concrete release/adoption plan for each case.
Decide what to group, publish, defer, or investigate and explain the costs and
next executable item. Include any tracking proposals needed to carry it out.
All work is planning-only. Do not create records, run CI, install, publish, or
modify repository/Git state. Write the plans in the supplied temporary directory.
