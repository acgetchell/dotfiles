---
name: cpp-api-design
description: "Design, review, and refactor modern C++23 public and cross-module APIs for cohesive contracts, safe ownership and value categories, constrained generic interfaces, predictable overload resolution, usable customization, and deliberate source/ABI evolution. Use when changes touch public headers or modules, exported types and functions, constructors or conversions, overload sets, templates, concepts, deduction guides, customization points, builders or fluent APIs, virtual interfaces, symbol visibility, exposed layout, or downstream consumer ergonomics."
---

# C++ API Design

Design public and cross-module C++ interfaces as long-lived caller contracts. Judge an API from realistic call sites, invalid-use prevention, diagnostics, and evolution cost—not only from the implementation that currently satisfies it.

## Ground Rules

- Read repository-local guidance and determine the supported compiler, standard-library, source-compatibility, and binary-compatibility contracts before changing an interface.
- Follow an explicitly declared language standard. When none is declared, use C++23 as the working design baseline but report the missing build contract. Treat C++26 as opt-in and do not introduce it until the user or repository explicitly chooses it after standardization and the supported toolchains implement the required facilities.
- Do not mutate git state unless the user explicitly asks in the current turn.
- Default to changed public or cross-module declarations plus representative consumers, implementations, tests, examples, and bindings needed to evaluate them.
- Preserve compatibility unless the user authorized a breaking change. Distinguish source, behavior, and binary compatibility rather than calling every signature edit an ABI break.
- Prefer the smallest cohesive surface. Do not add abstraction, genericity, overloads, fluent chaining, or customization points merely because C++ can express them.

Keep translation-unit, header self-containment, ODR/linkage, module-build, configuration, and compiler-matrix proofs under `cpp-build-portability`; ownership implementation and lifetime proofs under `cpp-lifetime-ownership-safety`; object validity under `cpp-invariant-state-transitions`; raw-to-domain boundaries under `cpp-parse-dont-validate`; failure guarantees under `cpp-exception-safety-error-contracts`; transformation design under `cpp-functional-style`; and semantic test strength under `cpp-test-quality`. This skill owns what callers can express, what misuse the interface permits, and how the public contract evolves.

When a public signature exposes a likely dangling lifetime, invalid state, or broken failure contract, record the caller-visible consequence and route deep proof and remediation to the owning specialist. Do not mark a neighboring review pass complete based on API analysis alone.

## Workflow

### 1. Map the contract and its consumers

Record:

- public, exported, cross-library, plugin, callback, FFI, and serialization-facing declarations in scope
- representative internal and downstream call sites, examples, tests, and language bindings
- required C++ standard and supported compiler and standard-library matrix
- source-, behavior-, and binary-compatibility promises
- ownership, lifetime, invalidation, failure, thread-safety, and complexity claims visible to callers

Do not infer a stable ABI solely from a shared-library build. Verify whether the project publishes such a promise and which platforms, compilers, build modes, and dependency versions it covers.

### 2. Keep the surface cohesive and minimal

Check:

- each type or function represents one clear domain responsibility
- names use caller-facing domain language rather than storage or algorithm accidents
- ordinary operations have one canonical path
- overloads, defaults, and convenience wrappers reduce caller decisions without creating ambiguity
- boolean parameters, sentinel values, output parameters, and call-order protocols are replaced by clearer types or operations when they admit misuse
- getters, setters, builders, and fluent stages expose only meaningful supported states and transitions
- public dependencies, includes, macros, and implementation types are no broader than necessary

Prefer ordinary value types and free functions when identity, inheritance, customization, or staged construction is not part of the contract.

### 3. Make parameters and results honest

Check that signatures communicate:

- ownership transfer, borrowing, nullability, mutation, lifetime, and invalidation
- value versus reference semantics and the cost of copying or materialization
- absence and failure without overloaded sentinel meanings
- units, coordinate systems, indices, handles, and other domain distinctions
- whether returned views, iterators, ranges, references, callbacks, or coroutine objects can outlive their sources

Use values by default when they are naturally small or independently owned. Use references, `std::span`, `std::string_view`, ranges, or other views only when the borrowing contract is safe and useful. Avoid returning `const` values, exposing mutable storage by accident, or using output parameters where a value result is clearer.

### 4. Control construction, conversion, and overload resolution

Check:

- single-argument constructors and conversion operators are `explicit` unless implicit conversion is intentionally part of the domain model
- invalid or narrowing conversions are rejected before entering the implementation
- overload sets have predictable selection for literals, integral widths, cv/ref qualifiers, derived types, initializer lists, and forwarding references
- lvalue, rvalue, `const`, and ref-qualified member behavior matches ownership and consumption semantics
- forwarding constructors and universal-reference overloads do not hijack copy/move construction or more specific overloads
- default arguments do not embed unstable policy or produce inconsistent behavior across call sites
- deleted overloads reject dangerous uses only when constraints cannot express the contract more clearly

Require a concrete caller benefit before adding an overload. A large overload set is not automatically an ergonomic API.

### 5. Constrain generic interfaces semantically

For templates, concepts, and customization points, check:

- constraints state the operations and semantic category the implementation actually requires
- requirements are neither accidentally stronger than the algorithm nor too weak to protect its body
- overload ordering and subsumption select one intended candidate
- diagnostics fail near the caller's mistake rather than deep inside an implementation
- deduction guides and class template argument deduction preserve the intended type and ownership semantics
- customization uses an established repository or standard-library pattern, with ADL exposure and fallback behavior understood
- hidden friends, tag dispatch, callable objects, and extension points do not expose implementation details or create collision-prone global hooks

Do not turn a closed set of supported types into a public template without a real extension requirement. Do not promise duck-typed behavior that tests cover for only one concrete type.

### 6. Preserve encapsulation and evolution paths

Check:

- public headers and modules expose only intentional declarations and dependencies
- symbol visibility and export annotations match the supported library boundary
- public layout, inheritance, virtual dispatch, exception specifications, enums, and calling conventions change only with the required compatibility review
- polymorphic bases have deliberate destruction, ownership, and extension contracts
- reserved extension space, PIMPL, type erasure, or versioned interfaces are used only when justified by an actual evolution or ABI requirement
- deprecations provide a working replacement, migration path, and removal policy

Do not recommend ABI indirection for a header-only or source-compatible library without an established binary contract. Conversely, do not dismiss layout or virtual-interface changes when downstream binaries are supported.

Use `cpp-build-portability` to prove that inline entities, explicit instantiations, module partitions, export annotations, and configuration-sensitive declarations compile and link consistently across translation units and supported configurations. This pass decides whether the exposed contract and its evolution are coherent.

### 7. Test the API as an external caller

Require the smallest evidence appropriate to the contract:

- minimal compile-pass consumers that include or import only the supported public surface
- compile-fail cases for rejected concepts, overloads, construction, and conversions when the harness supports stable negative compilation tests
- `static_assert`, `requires`, invocability, return-type, deduction, and `noexcept` checks for compile-time contracts
- representative call-site tests for lvalue/rvalue, move-only, borrowed, polymorphic, and customization behavior
- ABI comparison tooling only when the project claims a stable binary contract

Use `cpp-test-quality` to assess assertion strength and harness reliability. Match only stable constraint or error categories in compile-fail tests, not complete compiler-specific diagnostics.

Route multi-translation-unit, module-consumer, header self-containment, visibility, and explicit-instantiation evidence to `cpp-build-portability`; keep API tests focused on caller expressions and contract semantics.

### 8. Validate

Use the narrowest repository-documented validators that exercise downstream use. Prefer:

1. format and static analysis for changed declarations and implementations
2. direct compilation of minimal consumers and examples
3. focused compile-pass and compile-fail contract tests
4. affected runtime tests
5. affected language-binding builds when caller-facing bindings changed
6. ABI comparison against the intended baseline when binary compatibility is promised

Use `cpp-build-portability` for header-first consumers, multi-translation-unit or module builds, static/shared variants, and compiler/standard-library matrix validation. Verify current compiler and standard-library behavior from authoritative sources when feature support or overload behavior is version-sensitive.

## Finding Standard

For each finding, show the caller expression or evolution step that fails, the ambiguity or invalid state the API permits, the compatibility class affected, and the smallest coherent correction. Distinguish confirmed breakage from a design preference and do not report aesthetic API churn as a production defect.

## Handoff

Summarize public surfaces and representative consumers inspected, source/behavior/ABI contracts considered, invalid uses prevented, compatibility changes, compile-time and runtime evidence, validators and results, remaining migration work, and confirmation that no git state mutations were performed when true.
