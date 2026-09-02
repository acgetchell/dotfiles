# Platform Subprocess Evidence

Read this reference when support-script behavior depends on byte-sensitive or
platform-dependent subprocess transport.

## Transport Boundary

Trace the complete transport: producer bytes, stdout capture, intermediate
representation or storage, and consumer stdin. Make text versus binary
transport deliberate at both subprocess boundaries. If the contract is
byte-sensitive, capture producer stdout as bytes, preserve bytes between
processes, and send bytes without text-mode translation. A binary consumer
cannot recover CRLFs or non-UTF-8 data already changed or rejected by an earlier
text-mode stdout capture.

Verify producer and consumer bytes against a literal fixture or independently
computed digest. Use an actual child-process pipe when the regression concerns
stdout transport; a subprocess mock returning an already-decoded string does
not exercise newline conversion or decoding. A tool option that controls its
own newline or checkout behavior does not disable transformations performed
earlier by the host runtime, pipe, locale, or encoding layer.

For user-visible output, exercise the active stream encoding as another
boundary. Legacy Windows code pages can reject otherwise valid Unicode in
previews, status marks, release notes, paths, or next-step instructions. Render
or safely escape unsupported characters before an external mutation, and make
post-mutation reporting encoding-safe so a successful tag, upload, or publish
is not reported as a failed operation. Preserve the payload sent to the
external tool; escaping terminal output must not rewrite stored annotations.

For platform-dependent transport, separate a native run on the target platform
from a focused model or emulation of the transformation. Emulation is useful
for deterministic regression coverage but proves only the modeled boundary;
report the actual host and leave the native matrix cell unverified until it
runs there.

## Regression Sensitivity

Demonstrate sensitivity to the original behavior: the new case must fail
against the unfixed implementation or an exact isolated copy of its defective
boundary and pass after the correction. Do not weaken the assertion, skip the
test, or remove a supported platform cell when native CI exposes a missed
boundary.

Cover CRLF, mixed-newline, and non-UTF-8 producer output when bytes are
meaningful. For legacy output encodings, cover both representable input followed
by an unsupported status symbol and unsupported user-supplied preview content;
assert exit status, mutation count, unchanged external payload, and usable
next-step output.
