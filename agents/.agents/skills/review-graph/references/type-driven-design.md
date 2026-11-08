# Type-Driven Design

Shared modeling guidance for the Rust and Python parse-don't-validate skills.
Use it for design and review independently of review orchestration; follow the
calling skill for language-specific enforcement and scope.

## Start from the Domain, Not the DTO

Before choosing fields or implementing behavior:

1. List legal cases, facts required in each case, independent choices, and
   representative forbidden combinations.
2. Name each invariant and its canonical owner. Reuse an existing domain model
   rather than creating competing wrappers or sources of truth.
3. Distinguish structural restrictions, value/cross-field predicates, and facts
   about an owner or changing external world.
4. Sketch operation inputs and outputs: what evidence is required, and what
   evidence does success establish for the next operation?

For design work, use requirements and realistic callers even without an
implementation. For a review, demonstrate an admitted invalid state and its
consequence before calling a different representation a required fix.

## Choose Sums and Products Deliberately

A product combines facts that coexist. It admits combinations of its fields.
A sum chooses one alternative with only that alternative's required payload.
Match the representable cases to the supported domain cases.

For example, a delivery record containing a pickup flag, optional address, and
optional pickup point admits missing and contradictory payloads. Model the
choice as `Delivery = Ship(Address) | Pickup(PickupPointId)` instead
(language-neutral notation). An order can combine items with this delivery
choice as a product. An independent gift-wrap choice need not multiply every
delivery case.

This removes missing-payload states, not invalid address contents or an
unsupported item/destination pairing. Valid component values do not prove a
valid relationship between them; give that predicate an owning constructor or
operation. Document exactly what each type proves.

Use ordinary optional and success/failure types when they express the domain.
Introduce named alternatives when meanings or payloads differ. Keep booleans
for genuinely independent yes/no facts, not tags for dependent optional fields.

## Make Signatures Carry Evidence

Accept the state or refinement an operation needs rather than raw data plus a
validity flag. Return the established domain value or informative rejection,
not the original weak representation with discarded validation results.
Preserve evidence through internal helpers until a real output boundary needs
a primitive or wire representation.

Use stage types only when they prevent meaningful invalid ordering. A runtime
choice of state and compile-time restriction of available operations are
different needs; choose the simpler sufficient model. State what happens on a
failed transition, including whether the caller retains or can recover the
previous value. A stage name alone does not guarantee one-use behavior,
idempotency, atomic publication, or durable side effects.

## Establish, Preserve, and Consume the Proof

Keep raw transport shapes where compatibility requires them. Parse into the
domain before trusted computation, with runtime checks for predicates the type
shape cannot establish. Audit constructors, defaults, conversions, restore,
copy/update helpers, and deliberate bypasses.

Preserve the invariant through mutation and aliases. Bind owner-relative facts
to their owner/generation or check them at use. Existence, authorization, and
other external facts may expire after construction. Do not label an object
universally `Valid` when it establishes only a limited or temporary property.

Consume closed alternatives exhaustively so a new case exposes affected
callers. Do not silently map an unknown or unhandled state to a successful
known one. Open protocols and compatibility boundaries can need deliberate
unknown-case handling rather than an artificial closed world.

## Keep the Model Proportionate and Prove Its Benefit

Prefer existing types and standard refinements. Avoid per-field wrappers,
deep typestate hierarchies, or variant cross-products without a concrete
invalid state or misuse they eliminate. Keep passive reports, unconstrained
one-use values, and genuinely one-step operations simple.

Show supported caller examples and forbidden uses. Separate compiler/checker
evidence from runtime rejection tests and untested sketches. Verify negative
tests fail for the intended misuse, not unrelated errors. Cover remaining
predicates, reconstruction, and rejected updates independently of static shape.

Report the proposed types/signatures, invariant owners, remaining runtime
checks, and wire/API migration costs. Keep public concept placement and
compatibility with API-design specialists, coordinated mutation with the
state/production specialists, and mathematical validity with the scientific
specialists. Shared modeling does not duplicate their detailed proofs.
