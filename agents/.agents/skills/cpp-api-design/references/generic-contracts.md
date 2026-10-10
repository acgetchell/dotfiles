# Generic C++ Interfaces

## Constrain generic interfaces semantically

For templates, concepts, and customization points, check:

- constraints state the operations and semantic category the implementation actually requires
- requirements are neither accidentally stronger than the algorithm nor too weak to protect its body
- overload ordering and subsumption select one intended candidate
- diagnostics fail near the caller's mistake rather than deep inside an implementation
- deduction guides and class template argument deduction preserve the intended type and ownership semantics
- customization uses an established repository or standard-library pattern, with ADL exposure and fallback behavior understood
- hidden friends, tag dispatch, callable objects, and extension points do not expose implementation details or create collision-prone global hooks

Do not turn a closed set of supported types into a public template without a real extension requirement. Do not promise duck-typed behavior that tests cover for only one concrete type.
