# Validation Record Handoffs

Validation payloads and normalized records explicitly identify version 3.
Payload v1/v2 readers and handwritten commit `local_validation` declarations are
retired. Incoming evidence uses the immutable `VerifiedValidationRecord` variant
from the same evidence loader used by scheduling, journal admission and reports.

`load_validation_record(metadata_path=..., artifact_path=...)` exposes the typed
boundary. `validation_applicability(record, target=..., current_unit=...)`
compares current source/execution inputs and observes required artifacts without
running checks. Raw dictionaries exported from the record are report transport.

Repository-owned `review-validation-contracts.json` declarations match exact
command/directory pairs. Registry bytes are bound to their original captured Git
blob; implementation objects and selection membership are included. Workers can
add dependencies and limitations but cannot weaken that policy. Unknown commands
remain conservative. Reused source failures retain failure and blocked readiness.
