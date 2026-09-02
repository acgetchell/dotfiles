# Platform Regression Evidence

Read this reference when test confidence depends on an operating-system,
runtime, or byte-transport boundary.

## Exercise The Owning Boundary

Exercise the actual boundary rather than only a related application or tool
setting. For byte-sensitive stdin, stdout, files, hashes, signatures, or
archives, derive expected bytes independently from the production transform and
compare literal bytes or their independently computed digests. Cover text-mode
translation, encoding, and newline composition when reachable; do not assume a
downstream tool option controls earlier runtime or pipe conversion.

For subprocess pipelines, trace and test producer stdout capture, every
intermediate representation, and consumer stdin separately. Use a real child
process to emit CRLF, mixed-newline, and non-UTF-8 fixtures when stdout
transport owns the risk; a mock returning decoded text bypasses that boundary.

For command output, exercise a strict legacy encoding such as CP1252 in
addition to UTF-8 capture when Windows console behavior matters. Include output
emitted after a mocked successful external mutation. Assert the exit status,
exactly-once mutation, unchanged payload, and usable diagnostics or next-step
instructions so an encoding failure cannot masquerade as a failed tag, upload,
or publish.

## Prove Regression Sensitivity

Include durable focused coverage and a sensitivity check showing, through an
isolated copy or controlled fault injection, that the case fails with the
original behavior and passes with the fix. Keep captured source unchanged.

Label evidence as a native target-platform run, a model or emulation executed
on the actual host, or an unexecuted matrix cell. Emulation can prove the modeled
transformation but cannot establish native platform portability.

## Reconcile Native Evidence

Do not infer a platform pass from matrix configuration, a successful local
aggregate command, or emulation. When native CI contradicts earlier local or
modeled evidence, preserve the failure, strengthen the regression at the missed
boundary, and require current native evidence before restoring the portability
claim. Do not weaken or skip the regression or remove a supported platform cell
merely to make the matrix green.
