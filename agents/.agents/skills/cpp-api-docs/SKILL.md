---
name: cpp-api-docs
description: "Audit C++ public API documentation for caller contracts, Doxygen or generated-doc quality, headers and modules, templates and concepts, ownership and lifetime, invalidation, errors and exceptions, thread safety, complexity, examples, links, and discoverability. Use for public comments, API guides, generated reference sites, canonical examples, documentation warnings, and semver-relevant documentation changes. Route API design truth and executable test evidence to their focused C++ skills."
---

# C++ API Documentation

Audit documentation that teaches callers how to use a C++ API safely and correctly. Derive behavioral truth from declarations, implementations, tests, and the owning C++ specialists; do not let polished comments conceal an uncertain contract.

## Scope

Use changed public or cross-module documentation by default. Include nearby declarations, implementations, examples, bindings, and generated-doc configuration only as needed to establish the contract. Use whole-repository mode only when explicitly requested.

Follow the repository's declared C++ standard and support matrix. When none is declared, treat C++23 as the working baseline and report the missing build contract; do not introduce C++26 documentation claims without an explicit repository decision.

## Ownership Boundaries

- Own public documentation completeness, structure, discoverability, generated output, links, and example presentation here.
- Let `cpp-api-design` own disputed or non-obvious questions about whether the public interface and semantic contract are coherent.
- Let `cpp-lifetime-ownership-safety`, `cpp-exception-safety-error-contracts`, `cpp-concurrency-reentrancy`, `cpp-build-portability`, and `cpp-scientific-correctness` own non-trivial or disputed truths in their domains. Do not load them merely because this skill's caller-contract checklist names their concern; compare straightforward documentation claims with declarations, implementations, and existing tests here.
- Let `cpp-test-quality` own compile/runtime evidence for documentation examples and contracts.
- Let `repository-docs-review` own navigation and consistency across the wider documentation suite.

Reuse complete evidence from a C++ orchestrator pass for the same scope instead of repeating specialist reviews. Request a focused truth-owner handoff only when source evidence is inconclusive, a changed comment introduces or strengthens a consequential contract, or the user asks for that deeper audit.

Read [`references/doxygen.md`](references/doxygen.md) whenever Doxygen configuration, parsing, warnings, groups, cross-project links, XML output, or generated HTML/LaTeX is in scope. Do not load it for a comment-only review using another documentation system.

## Audit Workflow

1. Inventory the documented public surface: headers, exported modules, namespaces, types, functions, concepts, customization points, macros, constants, and bindings.
2. Identify the generated-document tool and its authoritative configuration.
3. Map each changed comment or guide to the declaration and behavior it claims.
4. Check caller contracts before wording and formatting.
5. Build documentation and compile canonical examples when the repository supports them.
6. Report undocumented or misleading behavior separately from documentation-tool failures.

## Caller Contract

Require documentation to state the non-obvious facts callers need:

- purpose and appropriate use
- preconditions and postconditions
- accepted ranges, units, coordinate systems, shapes, and encodings
- ownership, borrowing, lifetime, and aliasing expectations
- iterator, reference, pointer, span, view, handle, and callback invalidation
- errors, exceptions, error codes, and `noexcept` behavior
- strong, basic, or no failure guarantee when observable
- thread safety, reentrancy, synchronization, and callback restrictions
- complexity, allocation, blocking, and performance guarantees when contractual
- supported platform, compiler, feature, and configuration restrictions

Do not copy implementation mechanics into public comments. Explain why a constraint exists and what callers may rely on.

## C++ Language Surface

Check:

- templates name semantic requirements not already expressed by concepts
- concepts explain intent, associated semantics, and important exclusions
- overload sets and defaults make selection behavior understandable
- deduction guides, hidden friends, customization points, and ADL-sensitive APIs are discoverable
- module imports and header includes shown to callers match supported consumption paths
- aliases, re-exports, namespace organization, and feature guards appear correctly in generated docs
- unsafe or low-level APIs document representation, provenance, alignment, and lifetime obligations

Avoid documenting incidental compiler behavior as portable C++ and avoid claiming ABI or source stability without an established project policy.

## Structure And Discoverability

Check project, namespace, module, class, and function summaries for a coherent path from overview to detail. Related operations should cross-link without forcing readers to infer workflow from declaration order.

Verify headings, parameter and return descriptions, warnings, notes, and code blocks render as intended. Keep comments close to the authoritative declaration and avoid duplicate prose that can drift between headers, modules, and guides.

Document private helpers only when their intent preserves a non-obvious public invariant or generated private documentation is an intentional maintainer surface. Do not demand comments on obvious implementation details.

## Examples

Require examples for non-trivial workflows, constraints, ownership patterns, error handling, and configuration-sensitive use. Prefer the supported public include/import path and the smallest complete setup a caller can reproduce.

Check that examples:

- compile under the declared standard and relevant supported compilers
- avoid undefined behavior and undocumented lifetime assumptions
- handle fallible results according to the API contract
- do not depend on private headers, transitive includes, ambient using-directives, or repository-only paths
- remain synchronized with tests or named example targets when they define canonical usage

Route example assertion and matrix quality to `cpp-test-quality`.

## Generated Documentation

Treat Doxygen, Sphinx/Breathe, or another configured generator as the renderer, not the source of truth. Check warnings, broken references, missing inputs, duplicate anchors, undocumented public members according to policy, stale navigation, and generated-file ownership.

Do not hand-edit generated HTML, XML, tag files, or checked-in derived pages. Fix comments, configuration, templates, or source navigation and regenerate through the repository command.

## Validation

Prefer repository commands. Relevant focused evidence includes:

- documentation generation with warnings treated according to policy
- link and navigation checks
- compilation and execution of canonical examples
- minimal external consumers for include/import or feature claims
- supported compiler variants when documentation describes portability-sensitive behavior

Record unavailable generators, platforms, or compilers as limitations rather than implied passes.

## Output

Lead with misleading safety, lifetime, failure, concurrency, or portability contracts. Then report missing public coverage, discoverability and rendering failures, example problems, source-owner handoffs, validators run, and remaining evidence gaps.
