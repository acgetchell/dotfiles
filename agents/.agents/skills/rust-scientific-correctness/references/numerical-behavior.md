# Numerical Behavior

## Audit Numerical Behavior

Distinguish a poorly conditioned problem from an unstable implementation. Identify whether a claimed bound is absolute, relative, forward, backward, or residual-based, and verify that its units and assumptions match the result.

Inspect:

- overflow, underflow, cancellation, absorption, rounding accumulation, and unsafe reassociation
- NaN, infinity, signed zero, subnormal values, and non-finite intermediates
- arithmetic order, fused multiply-add behavior, reduction order, and platform-dependent backends
- tolerance scale, units, monotonicity, validation, and behavior under rescaling
- whether computing an error bound can itself overflow, underflow, or round non-conservatively
- exact-to-inexact conversion, representability, rounding mode, and loss-of-precision contracts
- consistency between approximate classification and exact results near decision boundaries

Do not accept a numeric sentinel, panic, or silent rounding where the public contract requires a typed failure or exact result.
