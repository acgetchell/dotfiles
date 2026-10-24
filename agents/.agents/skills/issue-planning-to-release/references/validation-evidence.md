# Validation Ownership and Reuse

Use when a plan proposes fewer CI runs, relocated checks, shared validators, or
artifact promotion. A proposed optimization must explain which guarantees remain
covered and why the evidence still applies.

## Map Guarantees Before Removing Work

For each guarantee record:

| Guarantee | Owner / issues | Validator | Required identity and context | Evidence location | Remaining work |
| --- | --- | --- | --- | --- | --- |
| Concrete supported behavior | Owning repository and issue links | Canonical recipe/job or public-package fixture | Source revision/tree, configuration, tools/inputs, platform/features, artifact as applicable | PR/check/run/attempt/artifact link, or explicitly pending | Missing proof, proposed consolidation, or satisfied gate |

Separate upstream installed-package fixtures from real consumer integration. The
former exercise supported public interfaces, distribution resources, and generic
failure cases in disposable representative projects. The latter verify published
version selection, real configuration/wiring, and the consumer's domain behavior.
Passing one does not imply the other, and upstream release completion owns only
its own acceptance and publication gates.

Do not delete consumer tests merely because similarly named upstream tests exist.
Identify the same guarantee, a supported published replacement, and any remaining
consumer-specific responsibility before proposing removal. Retain native checks
for platform-dependent tools, paths, line endings, features, and scientific work.

## Distinguish Source Evidence from Artifact Evidence

Reuse only under a supported contract whose identity and context are verified.
Evaluate repository/provider identity, tested checkout and source tree, workflow
definition, event/ref and trust context, tools and external inputs, configuration,
required jobs/platforms/features, run/attempt, freshness and conclusions. Preserve
the relationship to the protected release revision and any signer requirements.
Missing, failed, cancelled, ambiguous, stale, untrusted, or incomplete evidence
remains blocking; retain exact-commit fallback when equivalence cannot be proved.

Equal Git trees alone do not prove equivalent PR/main execution. They also do not
make artifacts interchangeable: Cargo archives can embed differing commit SHAs
in `.cargo_vcs_info.json`. A plan may reuse eligible source-validation evidence
while still requiring package construction/verification for the actual release
commit. Follow the repository's artifact reproduction or build-once promotion
contract and identify the exact retained files, IDs, and digests. Do not claim
native Cargo publication uploads byte-identical retained archives without proof.

Preserve approval-time revalidation, frozen evidence, trusted runtime/checkout,
protected environment and credential/OIDC boundaries, tag/release/asset policy,
and registry verification. Reusing a prior success cannot bypass those gates.
Registry visibility retries must follow the owning release guide and must not
silently repeat a publication mutation.

## Evaluate Cost Honestly

Identify job/setup/build/validator/report overlap from current recipes and workflow
composition. Use existing CI timing evidence where available; planning alone does
not authorize live CI or benchmark execution. Distinguish runner work eliminated
from time removed from the longest required path, accounting for parallelism,
queueing, and the next necessary publication/adoption gate.

Record unsupported savings as unknown and specify how authorized future work can
measure them. A faster validation loop must retain the original successful
behavior and coverage, including negative cases and scientific oracles. Keep
performance measurements separate from correctness requirements.
