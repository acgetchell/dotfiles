# Nonzero and Numeric Refinements

Load this reference when positive counts, bounded integers, dimensions, finite floats, probabilities, tolerances, or numeric conversion carry domain invariants.

## Integer Proofs

Prefer standard `NonZero*` types when the complete invariant is simply nonzero and storing the proof removes later checks. `Option<NonZero*>` can also encode absence without a zero sentinel.

Use a domain newtype when the contract is stronger or contextual, such as:

- at least three
- bounded by a supported dimension or capacity
- compatible with another field
- tied to an owner, generation, unit, or coordinate system

Keep raw integers in CLI/config/wire DTOs and tests that intentionally model rejection. Check negative values before unsigned conversion, perform narrowing deliberately, and handle arithmetic limits without overflow.

Do not convert a refined integer back to a primitive early and then recheck it downstream.

## Floating-Point Proofs

State the exact accepted set for each wrapper:

- finite only
- positive finite
- closed or open probability interval
- nonnegative tolerance
- logarithmic value that may allow negative infinity but rejects NaN or positive infinity

Specify NaN, infinities, signed zero, subnormal values, endpoints, normalization tolerance, and conversion behavior. A wrapper named `Finite*` must not silently accept a non-finite sentinel.

Keep scientific tolerance and error-bound validity under `rust-scientific-correctness`; this reference owns carrying an already chosen numeric contract in the type.

## API Shape

Use a fallible smart constructor and an infallible `get` or conversion whose cost and proof loss are clear. Preserve typed rejection categories through `rust-error-variants`.

Add boundary and property tests for smallest/largest valid values, every rejection class, overflow-adjacent conversions, non-finite values, endpoints, and round trips.
