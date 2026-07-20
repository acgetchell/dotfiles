# Scientific C++ Documentation

Load this reference when scientific documentation depends on C++ project metadata, public generated API sites, compiler support, CMake releases, or package consumption.

## Project And Release Coupling

Check consistency among the authoritative project version, README install examples, `CITATION.cff`, release notes, package-manager metadata, configured documentation version, and generated API landing pages. Identify whether CMake, a version header, release tooling, or another file owns the version; do not create competing literals.

Keep supported C++ standard, compiler and standard-library matrix, platforms, build options, optional dependencies, and feature/configuration claims aligned with build evidence. Route actual portability semantics to `cpp-build-portability` and command wiring to project tooling.

## API And Scientific Contracts

Route public comment coverage, Doxygen structure, examples, and generated reference warnings to `cpp-api-docs`. Route mathematical, geometric, stochastic, and numerical truth to `cpp-scientific-correctness`.

Check that scientific topic docs and API docs agree on:

- coordinate and indexing conventions
- ownership and lifetime of scientific data views
- dimensional and scalar-type support
- error and rejection behavior for invalid or degenerate inputs
- determinism, thread safety, and random-generator ownership
- compile-time or runtime feature requirements

## Generated Sites And Examples

Treat Doxygen/Sphinx/Breathe output as generated. Fix source comments, configuration, examples, or navigation and rebuild. Compile documented examples as consumers of installed or exported targets when they define canonical use; avoid repository-only include paths or transitive dependency assumptions.

Record auditable validation evidence: the wrapper and working directory,
documentation tool and compiler versions, configuration, generated output
artifacts, warnings, exit status, and installed/exported consumer checks.
Report unsupported or untested formats, compilers, and platforms instead of
broadening claims from the local build alone.
