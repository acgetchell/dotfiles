# Operational Acceptance for Release Workflows

Use when a plan changes release commands, workflow wiring, setup, verification,
or recovery. Keep executable procedures in the owning repository's release guide;
the plan identifies the commands, owners, evidence, and gaps needed to accept the
changed operator path. Existing evidence can satisfy unchanged requirements.

## Trace the Maintainer's Actual Path

Start with the documented entry command and expand transitive recipes, scripts,
and public CLI calls far enough to expose setup, repeated full validators,
provider requests, durable effects, and approval/credential transitions. Record
the working directory, tool version, argument and configuration forms, retained
inputs/outputs, and relevant permissions. A supported library call does not prove
that the installed CLI accepts the workflow's path or argument form.

A compact command map can carry the acceptance evidence:

| Command / transitive calls | Owner / issues | Boundary and retained state | Cost and job budget | Evidence / missing proof |
| --- | --- | --- | --- | --- |
| Actual maintainer invocation with arguments and working directory | Tooling or workflow owner and linked issues | Setup, verification, durable effect, approval or credentials | Setup, verification and effect time; repeated work/requests; timeout and margin | Installed-tool fixture, hosted run/attempt, or pending acceptance |

Count unrelated contributor-tool installation and nested duplicate audits, even
when hidden inside convenient recipes. Distinguish measured timings (with runner,
cache state, tool revision, and run/attempt), reported observations, request-count
estimates, and unknown costs. Request counts alone are not wall-clock evidence.
Budget the composed path, including cold setup and the applicable approval wait,
against its actual job timeout; distinguish elapsed time from total runner work.
If the timing or margin is unknown, name the measurement owner and leave that
acceptance pending. A timeout increase needs a justified budget and owner; it is
not evidence that the command now completes.

## Split Tooling Acceptance from Workflow Adoption

- **Shared tooling owner:** exercise installed public commands with representative
  arguments/configuration and safe provider fixtures. Cover real dispatch,
  packaged resources, path handling, verification, partial effects, and recovery.
  A transport fixture can simulate provider outcomes while keeping the actual
  command and orchestration code in use. Mocking the entire publisher or passing
  library unit tests alone does not establish the operator contract.
- **Workflow owner:** verify the real recipes, argument forms, pins/locks and
  configuration against the published supplying version, then collect authorized
  hosted bootstrap and composed-job timing on the relevant runner/cache state.
  Local fixture success does not establish hosted installation time, and static
  YAML checks do not establish either. Record the timing evidence separately.
- **Release/adoption tracker owner:** retain missing operational evidence and
  publication/adoption gates at their respective completion boundaries. Generic
  upstream fixtures can finish before real consumer adoption; later workflow
  timing does not make completed upstream implementation incomplete.

Use the smallest fixture and authorized hosted measurement that establish the
changed contract. Do not launch CI, acquire benchmarks, upload assets, or publish
to a registry merely to complete a planning checklist. If execution is outside
the authorization, specify the exact future command/context and its owner.

## Recover from Retained State

For each reachable failure below, identify durable local/provider state, the
supported inspection and next recovery command with its arguments, what it may
change, and the required verification/approval. Mark an unreachable case with
its reason; do not invent a new subsystem for it. Bound retries and define when
to stop for reconciliation. If the tooling has no ordinary recovery command,
map that gap to a bounded implementation issue; label proposed commands as
unimplemented rather than offering them as runnable instructions.

| Failure | Recovery contract to establish |
| --- | --- |
| Partial asset upload | Retain the manifest, evidence identities/digests, draft ID, and upload receipts; inspect provider state, verify matching assets, and resume only missing assets through a supported command. A conflicting asset must stop for reconciliation, not silent overwrite. |
| Failed verification | Preserve measurements and native evidence plus diagnostics; identify the failed input/context and use the documented repair/reverification command. Block effects until required verification passes. |
| Ambiguous draft creation | Reconcile by stable release identity and inspect the provider for the existing draft before retrying creation. Stop on conflicting or ambiguous matches. |
| Timeout | Determine which boundary was reached and reconcile any in-flight effects; reuse eligible retained work and resume at the supported boundary with a justified setup/job budget. |
| Approval interruption | Retain frozen selection and evidence identity, reconcile effects if interruption occurred after approval, then return through the supported approval path, including required freshness revalidation before credentials/effects. |

Do not default to cleaning retained state, retagging, reacquiring benchmarks, or
inventing a new acceptance selection. A workflow failure alone does not invalidate
valid measurements or signed/native evidence. Reuse remains subject to
[validation evidence](validation-evidence.md): preserve source/context/artifact
identity, scientific checks, freshness, and approval-time revalidation. If a
specific input is invalid, scope the necessary recomputation to that finding and
its authorization. A fail-closed stop is a safeguard, not successful recovery;
acceptance must also prove the supported successful continuation.

## Keep Gates Proportional

For each added gate name the requirement or concrete risk, owner/issues, evidence
needed, blocking status, and added maintainer steps, latency, or permissions.
Separate required release acceptance from optional hardening. Consolidate repeated
work only after mapping equivalent guarantees; preserve required reports,
scientific coverage, freshness checks, and credential/approval transitions.

A conventional release with unchanged commands and sufficient current evidence
can retain its existing gates and ordinary recovery procedure. Do not require a
new architecture, exhaustive audit, extra approval, or live operation simply
because a plan contains a release. End with the executable next item, or the
specific missing command/evidence that prevents it, and its owner and issues.
