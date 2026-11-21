---
name: python-style-hygiene
description: Review Python docstrings, naming, imports, and readability during Python code reviews or focused style work. Use for whole-repo style baselines and callable documentation audits.
---

# Python Style Hygiene

Review Python implementations and examples for readable contracts and idiomatic code. Use this skill directly or as a specialist pass in a broader review. Follow the repository's documented and enforced conventions, using [PEP 8](https://peps.python.org/pep-0008/) and [PEP 257](https://peps.python.org/pep-0257/) as defaults.

## Scope and evidence

- In a change review, inspect changed functions, relevant neighboring imports, and direct callers. Include private implementation and examples within that scope.
- For a whole-repo baseline, inventory first-party modules, scripts, tests, stubs, and examples. Inspect documented exports, registered entry points, cross-module helpers, and nontrivial internals. Identify generated or vendored code and report any unevaluated scope.
- Use AST or configured lint results to find missing docstrings, imports, and other candidates. A public-looking name, lint warning, or docstring count is a lead. Verify against exports, call sites, the implementation, and consequential tests.
- Report missing or misleading contracts separately from optional readability work. Give a location, the information a reader needs, and a concrete edit. When asked to fix findings, preserve supported imports, signatures, behavior, and test evidence.

## Read the relevant guidance

| Area | Apply when | Sources |
| --- | --- | --- |
| Docstrings and comments | Reviewing functions, methods, classes, modules, or documentation attached to code. Read [Callable documentation](references/callable-documentation.md). | [PEP 257](https://peps.python.org/pep-0257/), [Real Python docstrings](https://realpython.com/ref/best-practices/docstrings/), [Real Python comments](https://realpython.com/ref/best-practices/comments/) |
| Naming and visibility | Reviewing names, policy constants, scope, or code that hides external effects. Read the naming section of [Naming, imports, and readability](references/naming-imports-readability.md). | [PEP 8 naming](https://peps.python.org/pep-0008/#naming-conventions), [Real Python functions](https://realpython.com/ref/best-practices/functions/), [Real Python public API surface](https://realpython.com/ref/best-practices/public-api-surface/) |
| Imports and control flow | Reviewing import placement, qualification, conditions, loops, or exception handlers. Read the matching sections of [Naming, imports, and readability](references/naming-imports-readability.md). | [PEP 8 imports](https://peps.python.org/pep-0008/#imports), [Real Python imports](https://realpython.com/ref/best-practices/imports/), [Real Python coding style](https://realpython.com/ref/best-practices/coding-style/), [Real Python Pythonic code](https://realpython.com/ref/best-practices/pythonic-code/) |

For public call shape and compatibility, apply [python-api-design](../python-api-design/SKILL.md). For installed imports, platform-specific imports, and packaging, apply [python-build-portability](../python-build-portability/SKILL.md). For substantial consolidation, apply [python-simplification-review](../python-simplification-review/SKILL.md).

Use the owning regression if an edit changes execution or exported documentation. For documentation-only changes, verify the docstring is attached to the intended object and use the project's relevant checks. Follow the review graph's [typed results](../review-graph/references/typed-results.md) when dispatched by that workflow.
