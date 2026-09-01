# Platform Subprocess Evidence

Read this reference when support-script behavior depends on byte-sensitive or
platform-dependent subprocess transport.

## Transport Boundary

Make text versus binary transport deliberate at every subprocess boundary. If
the consumer's contract is byte-sensitive, send bytes without text-mode
translation and verify the bytes the child consumed against a literal fixture
or independently computed digest. A tool option that controls its own newline
or checkout behavior does not disable transformations performed earlier by the
host runtime, pipe, locale, or encoding layer.

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
