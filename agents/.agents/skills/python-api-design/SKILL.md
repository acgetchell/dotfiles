---
name: python-api-design
description: "Design or review material Python public and cross-module API changes for caller usability, precise contracts, and compatible evolution."
---

# Python API Design

Judge reusable interfaces from representative callers, concept ownership, and
evolution cost. A convenient implementation does not establish a usable public
contract.

## Scope And Ground Rules

- Honor the supplied scope. For direct invocation, default to changed public or
  materially shared interfaces plus their implementations, consumers, tests,
  examples, and stubs. Review the whole surface only when requested.
- Establish the supported Python floor, type checker, public import paths,
  downstream consumers, and compatibility promises from repository guidance.
- Treat documented imports, re-exports, stubs, protocols, callbacks, and
  subclassing hooks as potential contracts. Neither a leading underscore nor
  `__all__` alone establishes how consumers actually use a module.
- Preserve compatibility unless a breaking change is authorized. Reviews are
  read-only; requested fixes authorize local edits and relevant checks, not Git
  mutations or publication.
- Prefer the smallest cohesive interface. Add classes, protocols, wrappers,
  overloads, or extension points only for a concrete caller benefit. Private
  helper cleanup alone does not require this skill.

## Ownership Boundaries

Own concept placement, canonical public paths and workflows, callable and type
contracts, caller-visible effects, and API evolution here. Keep:

- raw-to-trusted conversion and invariant enforcement under
  `python-parse-dont-validate`
- artifact contents, installed importability, runtime/platform compatibility,
  and annotation evaluation under `python-build-portability`
- CLI argument/output behavior under `python-cli-review`
- mathematical validity under `python-scientific-review`
- durable assertion and fixture quality under `python-test-quality`
- coordinated mutation, cleanup implementation, concurrency, security, and
  integration synthesis under `python-production-review`

Record the caller-visible consequence of a neighboring defect and hand off its
deep proof. Do not claim that contract is complete from API evidence alone.
Documentation reviewers own completeness and navigation; this pass establishes
whether documented caller expressions and promises match the interface.

## Map Concepts And Caller Workflows

Identify the public functions, classes, constructors, methods, properties,
protocols, callbacks, aliases, and exported names in scope. Inspect realistic
internal and downstream call sites, examples, and `.pyi` declarations where
present. Record each concept's responsibility, owning module, supported import
path, normal workflow, and extension contract.

Check that one module owns each concept, dependency types are exposed
deliberately, and adapters add actual translation or policy. Keep independent
capabilities composable without parallel families of classes or methods. Give
ordinary operations one preferred path; alternate constructors, aliases, and
wrappers should serve a distinct caller or compatibility need. Preserve distinct
units, invariants, and semantic roles even when structures look similar.

## Make Calls And Results Unambiguous

- Check positional-only and keyword-only boundaries against actual callers.
  Renaming a keyword-capable parameter can break callers even if its position
  and type remain unchanged.
- Check defaults for mutable shared state, policy surprises, and whether
  omitted, explicitly `None`, and invalid input have distinct meanings. Use a
  sentinel only when callers need that distinction.
- Require a concrete compatibility or forwarding need for broad `*args` and
  `**kwargs`; they should not hide required fields or swallow misspelled options.
- Replace ambiguous boolean combinations, output containers, sentinel results,
  and undocumented call ordering when a clearer contract materially helps.
- Make absence, failure, result shape, and exception categories distinguishable
  according to caller needs. Preserve deliberate local exception conventions.
- Check constructors, dataclass fields, properties, equality, hashing, and
  subclass overrides only where they are part of the consumer contract.

## Make Typing Describe Runtime Behavior

Check public annotations and stubs against accepted arguments, runtime results,
and supported Python/type-checker configurations. Prefer the least demanding
input capability the operation actually uses; do not require a concrete list,
mapping, or collaborator class when a narrower contract serves consumers.

Use protocols for meaningful structural collaborators, generics for real
relationships between inputs and outputs, and overloads for supported caller
distinctions. Check callback parameter kinds, return values, override
compatibility, and whether overloads agree with the implementation. Flag `Any`,
casts, or ignores that conceal a public mismatch, rather than treating every
dynamically typed boundary as defective. A static protocol annotation is not
runtime validation.

When the Python floor or annotation evaluation changes, consult
[annotation compatibility](../python-build-portability/references/annotation-compatibility.md)
and route the runtime/version proof to portability. Preserve the project's
established checker instead of adding another toolchain.

## Expose Effects And Lifetime Honestly

Check whether callers can determine input consumption, mutation, aliasing,
copy-versus-view behavior, and eager-versus-lazy execution. An iterable may be
one-shot; repeated traversal or a promise of reusable results needs supporting
evidence.

For generators, context managers, callbacks, and async operations, establish who
owns resources or tasks, when work and exceptions occur, and how early exit,
partial iteration, cancellation, or closing affects the caller. Review the
public contract here; route cleanup, race, and rollback implementation proofs to
production review. Do not silently turn a synchronous operation into an async
one or eager results into deferred work as an ergonomic cleanup.

## Protect Evolution And Validate As A Caller

Compare the intended interface with its baseline and representative consumers.
Distinguish import-path, call-signature, typing, extension, and behavioral
compatibility. Include keyword names, defaults, return shapes, exception
categories, mutability, evaluation timing, and supported subclass/protocol
implementations. Deprecations need a usable replacement and migration path.

Choose the smallest evidence that exercises the material claim: public-import
examples, representative positional/keyword calls, configured type checks,
callback/protocol implementations, and affected runtime tests. Add negative
typing cases only when the existing harness supports durable rejection tests.
Use built/installed consumers through portability when distribution behavior is
at issue. Reuse a supplied validation ledger; do not repeat current evidence or
run full CI merely because this pass is complete.

## Output

For a design request, show the proposed interface with realistic caller examples
and explain material tradeoffs and migration needs. For a review, follow the
parent result contract when supplied; otherwise report scope and `PASS`,
`NEEDS IMPROVEMENT`, or `FAIL`, with findings ordered by severity.

For each finding, identify the public item and representative caller expression,
the concrete misuse, breakage, or evolution cost, the compatibility class, and
the smallest coherent correction. Separate demonstrated defects from optional
design preferences. Report validation performed or reused, specialist handoffs,
and meaningful limitations.

Review outcomes: [typed contract](../review-graph/references/typed-results.md); read on rejection. Missing evidence stays blocked.
