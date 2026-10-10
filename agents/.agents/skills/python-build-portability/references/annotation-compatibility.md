# Annotation Compatibility

Read when changing annotation evaluation, runtime type introspection, or the
supported Python floor. Check the actual floor and consumers before removing
compatibility imports. Python 3.14 defers annotations by default, while
`from __future__ import annotations` retains stringified semantics. For a
3.14-or-newer-only project, remove an obsolete import when this work is in scope;
retain it when an intentional runtime consumer requires that representation and
verify the consumer. Do not expand an unrelated review into annotation cleanup.
