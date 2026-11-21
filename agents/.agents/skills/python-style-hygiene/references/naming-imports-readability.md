# Naming, imports, and readability

## Naming and visibility

- Match repository terminology. Use `snake_case` for functions and variables, `CapWords` for classes, and `UPPER_CASE` for module constants where the existing conventions apply.
- Prefer names that describe the operation and result at the call site. Differentiate `parse_manifest`, `read_manifest`, and `publish_manifest` according to the effects they actually have. Include units such as `timeout_s` or `size_bytes` when a bare number would invite mistakes. Use short conventional names within small scopes where their meaning is clear.
- Use distinct local names when a transformation changes what a value represents, such as `manifest_text` for input and `manifest` for the parsed result. Name a literal when the name explains a policy, such as `MAX_REDIRECTS`. Share a constant only when the uses should change together. See Real Python on [variables](https://realpython.com/ref/best-practices/variables/) and [constants](https://realpython.com/ref/best-practices/constants/).
- Examine vague verbs such as `process` or `handle` against neighboring code. Keep a prefix if it distinguishes operations, such as `get_cached_record` and `fetch_record`. Reserve single leading underscores for implementation detail according to the repository's visibility convention. Treat `__all__`, re-exports, fixture names, CLI destinations, and public keyword arguments as possible compatibility boundaries.
- Flag a public name that obscures an effect or misleads callers. Prefer correcting its docstring or routing an API change to the API-design pass when renaming would affect callers.

See [PEP 8 naming conventions](https://peps.python.org/pep-0008/#naming-conventions), [Real Python's function practices](https://realpython.com/ref/best-practices/functions/), and [Real Python's public API guidance](https://realpython.com/ref/best-practices/public-api-surface/).

## Imports and qualification

- Keep ordinary imports at module scope, grouped as standard library, third party, and first party. Follow the repository's absolute or explicit relative import convention and let its configured tooling handle order. Review wildcard imports, especially where they obscure origin. Verify any intentional public re-export against the package API.
- Prefer module qualification when it identifies a domain, prevents a collision, or groups several uses of the same dependency. Use a direct import when qualification repeats long paths and the direct name is clear at each call site. Keep conventional aliases and aliases that resolve an actual conflict.
- Preserve intentional local imports that defer optional dependencies, expensive initialization, or imports that participate in a cycle. Preserve runtime imports used by annotation introspection, registration, or plugins. Before moving such an import, check module initialization, import order, available extras, and the normal installed or CLI entry point.
- If an import appears unused, inspect `__all__`, public re-exports, runtime registration, and runtime annotation consumers before removing it.

See [PEP 8 on imports](https://peps.python.org/pep-0008/#imports) and [Real Python's import practices](https://realpython.com/ref/best-practices/imports/).

## Control flow and readability

- Read the success path, error exits, and cleanup as a caller would experience them. Use guard clauses where they expose preconditions or reduce indentation without changing exception handling, cleanup, or the order of side effects.
- Check which inputs should take the same branch before suggesting `if value` or `value or default`. If `None` selects the default retry limit and `0` disables retries, use `if retries is None` to preserve the explicit zero. See [Real Python on conditionals](https://realpython.com/ref/best-practices/conditionals/).
- Keep a `try` block scoped to the operations its handler can recover from. If `except KeyError` reports a missing record, put only `records[key]` in the block and call `render(record)` after a successful lookup. A `KeyError` raised during rendering then retains its own meaning. See [PEP 8 programming recommendations](https://peps.python.org/pep-0008/#programming-recommendations) and [Real Python on exception handling](https://realpython.com/ref/best-practices/exception-handling/).
- Prefer iteration over elements, `enumerate()` when an index matters, and a short comprehension for a simple transform. Use an ordinary loop when validation, branching, repeated work, or effects need to be visible. Before replacing a loop or comprehension, check iteration order, short-circuiting, and whether callers can pass single-use iterables.
- When pairing inputs, check what should happen if their lengths differ. Plain `zip()` stops at the shorter input. When every filename needs a corresponding checksum, `zip(..., strict=True)` (Python 3.10+) raises `ValueError` when iteration reaches the mismatch. Preserve intentional truncation. See [Real Python on loops](https://realpython.com/ref/best-practices/loops/) and [Python's `zip()` reference](https://docs.python.org/3/library/functions.html#zip).
- Keep effectful operations visible in call names and docstrings. When a simplification changes when I/O occurs, which exceptions callers see, or how results are evaluated, classify it as a behavior change and verify the owning test.
- Follow the repository formatter. Report readability issues that still matter after formatting with the specific expression, call, or control flow that caused confusion.

See [Real Python's coding style](https://realpython.com/ref/best-practices/coding-style/) and [Real Python's idiomatic Python practices](https://realpython.com/ref/best-practices/pythonic-code/).
