# Callable documentation

## Decide what needs a docstring

Read the declared signature, representative callers, and any tests that define an edge case. Inspect `__all__`, re-exports, documented imports, package entry points, and protocol or base-class definitions to identify callers' entry points. Docs generated from runtime introspection usually read the implementation, class, or property docstring.

- Give each exported callable a summary. Give packages, modules, and public classes a summary that helps callers locate the right interface. For a class, document construction, ownership, or lifetime at the class or constructor where the repository's documentation renders it.
- Document private or cross-module helpers that own meaningful rules. Examples include state changes, a non-obvious sentinel, iteration order, resource cleanup, or the distinction between an absent artifact and invalid evidence.
- Put a uniform contract on the protocol, base method, or implementation behind overloads. Overrides need their own documentation when they add a caller-visible guarantee or prerequisite. Check where generated documentation picks up the text.
- Descriptive test names can explain small cases. Explain why a fixture, parametrization, or test setup is necessary when it recreates a hidden precondition or keeps a past regression reproducible.

See [PEP 257 on where docstrings belong](https://peps.python.org/pep-0257/#what-is-a-docstring) and [Real Python's docstring practices](https://realpython.com/ref/best-practices/docstrings/).

## Write and verify the contract

1. Put the docstring first in the body. For a function or method, summarize its action in the imperative. For a class, describe what an instance represents. For a module or package, summarize what it provides. Keep a single line when it carries the full contract. For a multiline docstring, leave a blank line after the summary, use the project's section format, and put the closing triple quotes on a separate line.
2. Document choices the type signature leaves open. Include units, expected formats, relative path bases, defaults with operational meaning, and precedence between sources when those details affect callers.
3. Explain ambiguous outcomes. Say what an empty collection or `None` means, when results are ordered or deduplicated, and whether the function returns a view, copy, iterator, or caller-owned resource. For lazy or asynchronous work, explain when validation, I/O, and cleanup happen if timing matters.
4. Describe effects and recovery conditions that callers can act on. Identify output locations, mutation of caller data, network or subprocess work, expected exceptions, retry effects, and the state a failed operation leaves behind. Confirm every guarantee by inspecting failure paths.
5. Add a short example when it explains a non-obvious call sequence or result. Use doctest syntax when the project exercises it, and verify the example with the repository's supported commands. Keep duplicate type declarations out of prose unless the project's renderer requires them.

See [PEP 257 on one-line docstrings](https://peps.python.org/pep-0257/#one-line-docstrings), [PEP 257 on multiline docstrings](https://peps.python.org/pep-0257/#multi-line-docstrings), and [Real Python's comparisons of docstring formats](https://realpython.com/ref/best-practices/docstrings/).

### Examples

```python
def default_report_path(root: Path) -> Path:
    """Return the default report location beneath the repository root."""
    return root / "reports" / "summary.json"
```

```python
def load_cached_manifest(path: Path) -> Manifest | None:
    """Read and validate the retained manifest.

    Return None when the file is absent. Raise ManifestError when the file
    exists but cannot be parsed or authenticated.
    """
    ...
```

A summary such as “Load the manifest” leaves both absence and failure ambiguous. Confirm the implementation distinguishes those outcomes before documenting them. A lookup that uses a different root or follows a search order should disclose it in the contract.

## Keep comments local to the rationale

Use comments for a choice that matters to a maintainer, such as preserving sort order for a file format, delaying an import to preserve optional dependency behavior, or applying an upstream workaround. Give a specific reason or link to the relevant issue when available. Keep facts callers depend on in the docstring. During edits, verify that comments still describe the branch, invariant, or workaround they accompany. See [PEP 8 on comments](https://peps.python.org/pep-0008/#comments) and [Real Python's comment practices](https://realpython.com/ref/best-practices/comments/).
