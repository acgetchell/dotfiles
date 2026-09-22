# Dispatch Overhead Measurement

The September 2026 structural replay compared the runtime at commit
`eeead7c646a45ca8227bc7fc057e6f2e1bdf52bf` with the publication, shared-packet,
and prompt changes for issue #72. Both used the same current planner, schemas,
and skill files to isolate dispatch protocol costs.

The synthetic fixture had 18 Python/tooling/documentation files and 15 nodes:
nine focused audits, one independent review, three validators, and two syntheses.
The plan configured four slots. Five materializations ran per version. No model
workers or validation commands ran; this does not measure end-to-end review
latency, actual worker source reads, or semantic recall.

| Measurement | Before | After |
| --- | ---: | ---: |
| Worker wrapper bytes | 336,944 | 253,768 |
| Prompt text bytes | 107,980 | 22,928 |
| Separate shared source packet bytes | 0 | 3,800 |
| Required publication process invocations for 15 workers | 30 | 15 |
| Median materialization time | 33.25 ms | 34.64 ms |

The packet represented 18 distinct files that otherwise appeared in 66 audit
file requests. Those counts describe potential read demand; worker reads were
not observed. Prompt bytes are a subset of wrapper bytes. Packet bytes are
additional storage. Publication counts come from the protocol, not a timed
publication run. Small timing differences are not evidence of a speedup.

For a live follow-up, retain the captured plan/source identity and dispatch
telemetry, record worker source reads and coordinator invocations, and measure
elapsed time and adjudicated findings under the same four-slot budget. Compare
blocked and recovered attempts separately from successful validation. Keep the
independent reviewer blind to specialist conclusions and shared packets.
