# Doxygen Review

Load this reference when Doxygen configuration, parsing, warnings, groups, cross-project links, XML output, or generated HTML/LaTeX is in scope. Follow repository commands and the installed Doxygen version rather than assuming every option exists everywhere.

## Inputs And Extraction

Check the effective `Doxyfile` and any generated fragments for:

- explicit `INPUT`, working directory, recursion, exclusions, and file patterns
- C++ header, implementation, module-interface, and auxiliary `.dox`/Markdown coverage
- extension mappings for non-standard file suffixes
- preprocessing configuration for feature macros and declaration annotations
- include paths and stripped source prefixes that affect displayed names
- public/private/static extraction matching the intended audience

An empty `INPUT` makes the current directory significant. Treat the invocation directory as part of the command contract. Do not use `EXTRACT_ALL = YES` merely to hide missing documentation: it changes extraction semantics and disables undocumented-member warnings.

Verify that comments attach to the intended declaration, overload, specialization, concept, namespace, file, group, or module. Watch for comments placed only on definitions when headers/modules are the public source, anonymous namespaces leaking into output, and macros that cause Doxygen to parse a different declaration from the compiler.

## Warnings As Evidence

Keep general and documentation-error warnings enabled. Select warning policy deliberately:

- undocumented public members and enum values according to project policy
- incomplete or incorrect parameter, template-parameter, return, and exception documentation
- broken commands, references, layout elements, and included snippets
- warnings promoted to a failing exit only after known noise is resolved or narrowly accounted for

Avoid configurations where a successful process merely produced warning-filled output. Capture warning logs as diagnostics, not generated source. When using `WARN_AS_ERROR`, prefer a mode that completes the scan and returns failure after collecting warnings if repository tooling supports it.

## C++ Entities And Commands

Check Doxygen's model against the public C++ surface:

- use module, namespace, file, concept, class, function, macro, and group commands only when automatic attachment is insufficient
- document every template parameter whose semantics are not already clear from a concept
- ensure overload-specific comments describe the actual difference rather than relying on generic generated text
- keep member sorting from separating overload documentation that depends on relative order
- use explicit references when automatic linking is ambiguous, especially for overloads and qualified names
- show the supported header or module import for public concepts and grouped members

Test Markdown and Doxygen commands in the generated output. Backslashes, `@` commands, fenced code, headings, lists, angle brackets, and XML-style comments can be parsed differently depending on context; source readability alone is not rendering evidence.

## Navigation, Groups, And Links

Check that groups form a stable information hierarchy without duplicating or hiding namespace/class navigation. Verify unique page/section anchors, related-member groups, search visibility, and links from overview pages into the public reference.

For external projects, validate generated/imported tag files, unique tag names, and `TAGFILES` destinations. Relative tag-file locations are interpreted from generated output, so test deployed links rather than only local source paths. Do not ingest third-party sources solely to obtain links when an external tag file is the intended boundary.

## XML And Downstream Renderers

When Sphinx/Breathe, custom indexing, or another consumer uses Doxygen XML:

- verify `GENERATE_XML`, output paths, namespaces, and source-listing policy
- treat XML schema/output changes as compatibility-sensitive for downstream consumers
- test the downstream renderer rather than assuming successful XML generation proves usable documentation
- keep generated XML, HTML, LaTeX, tag files, and search indexes under declared generated-output ownership

Disable unnecessary source/program listings when they create large artifacts or expose implementation the published docs should omit.

## External Tools And Portability

Check optional Graphviz, LaTeX, BibTeX, Perl, image, and search dependencies only when enabled. Resolve their paths through repository tooling or Doxygen's configured external-tool path rather than a developer's interactive shell. Record unavailable formats separately: successful HTML generation does not prove PDF/LaTeX or diagram output.

## Focused Validation

Prefer the repository wrapper. Otherwise inspect the effective configuration and run Doxygen from the documented working directory, preserving warnings and exit status. Then validate the actual consumers in scope:

- generated HTML navigation and links
- XML plus Sphinx/Breathe or other downstream build
- external tag-file links
- LaTeX/PDF output when published
- compiled example/snippet sources when they define caller behavior

Report the Doxygen version, configuration path, enabled output formats, warnings, downstream validators, and formats not exercised.
