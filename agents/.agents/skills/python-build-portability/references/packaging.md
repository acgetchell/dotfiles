# Python Packaging and Installation

## Packaging And Installation

Check:

- build requirements and backend configuration are complete and mutually consistent
- package discovery, namespace packages, and source layout include the intended modules
- wheels and sdists contain required modules, type information, templates, schemas, licenses, and package data
- imports do not succeed only because the repository root is on `sys.path`
- generated version/source files exist in clean builds without untracked state
- editable installs do not mask failures in built artifacts
- package resources replace source-relative file access
- build hooks do not depend on ambient executables, network, working directory, locale, or machine paths without an explicit contract

Compare wheel and sdist contents when either could diverge. Test the built wheel from outside the repository.

Inspect archives and metadata with uv, platform archive tools, the standard library, or an existing repository validator. Do not add one-off packaging checker dependencies when direct inspection provides the required evidence.
