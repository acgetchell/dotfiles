"""Read skill frontmatter with consistent safe YAML and mapping-key semantics."""

import re
from collections.abc import Hashable
from typing import Any, cast, override

import yaml
from yaml.constructor import ConstructorError, SafeConstructor
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)
_YAML_MERGE_KEY = sentinel("_YAML_MERGE_KEY")
_MERGE_TAG = "tag:yaml.org,2002:merge"


class _SkillMergeConstructor(SafeConstructor):
    """Apply YAML merge precedence before the safe constructor builds Python values."""

    @override
    def flatten_mapping(self, node: MappingNode) -> None:
        """Keep explicit keys and earlier merge sources at higher precedence."""
        merges = [value for key, value in node.value if key.tag == _MERGE_TAG]
        if merges:
            # Detach merge edges before descending so recursive aliases terminate.
            node.value = [(key, value) for key, value in node.value if key.tag != _MERGE_TAG]
            # Visit highest precedence first. A shared key/value node pair needs
            # one slot even when several aliases inherit it through different maps.
            pairs = dict.fromkeys(reversed(node.value))
            for merge in reversed(merges):
                sources = merge.value if isinstance(merge, SequenceNode) else [merge]
                for source in sources:
                    if not isinstance(source, MappingNode):
                        raise ConstructorError(None, None, f"expected a mapping to merge, found {source.id}", source.start_mark)
                    self.flatten_mapping(source)
                    pairs.update(dict.fromkeys(reversed(source.value)))
            # PyYAML assigns keys in sequence, so the highest precedence goes last.
            node.value = list(reversed(pairs))
        super().flatten_mapping(node)


class PythonSkillLoader(_SkillMergeConstructor, yaml.SafeLoader):
    """Load skill YAML with the Python safe loader."""


SAFE_YAML_LOADER = PythonSkillLoader
if hasattr(yaml, "CSafeLoader"):

    class CSkillLoader(_SkillMergeConstructor, yaml.CSafeLoader):
        """Load skill YAML with the optional LibYAML parser."""

    SAFE_YAML_LOADER = CSkillLoader


def load_safe_yaml(text: str) -> Any:
    """Construct a document with the selected safe loader and release resources."""
    loader = SAFE_YAML_LOADER(text)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def construct_scalar_mapping_key(node: ScalarNode, loader: SafeConstructor) -> Hashable:
    """Construct a key identity without flattening away explicit duplicates."""
    if node.tag == _MERGE_TAG:
        # A merge directive is distinct from a literal quoted '<<' key.
        key = _YAML_MERGE_KEY
    elif node.tag == "tag:yaml.org,2002:value":
        # SafeLoader normalizes this mapping-context tag to a string.
        key = node.value
    else:
        key = loader.construct_object(node, deep=True)
    if not isinstance(key, Hashable):
        raise ConstructorError(None, None, "found unhashable key", node.start_mark)
    return key


def find_duplicate_mapping_key(node: Node | None, loader: SafeConstructor) -> str | None:
    """Return the first repeated scalar mapping key in a YAML node tree."""
    if node is None:
        return None
    pending = [node]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, MappingNode):
            seen: set[object] = set()
            for key_node, value_node in current.value:
                if isinstance(key_node, ScalarNode):
                    key_value = cast("str", key_node.value)
                    key_identity = construct_scalar_mapping_key(key_node, loader)
                    if key_identity in seen:
                        return key_value
                    seen.add(key_identity)
                pending.extend((key_node, value_node))
        elif isinstance(current, SequenceNode):
            pending.extend(current.value)
    return None


def frontmatter_text(content: str) -> tuple[str | None, str]:
    """Extract a delimited YAML header from a Markdown document."""
    if not content.startswith("---"):
        return None, "No YAML frontmatter found"

    match = FRONTMATTER_RE.match(content)
    if match is None:
        return None, "Invalid frontmatter format"
    return cast("str", match.group(1)), ""


def parse_frontmatter(frontmatter_text: str) -> tuple[dict[str, object] | None, str]:
    """Reject explicit duplicate keys before resolving merges in the same YAML document."""
    try:
        loader = SAFE_YAML_LOADER(frontmatter_text)
        try:
            node = loader.get_single_node()
            duplicate_key = find_duplicate_mapping_key(node, loader)
            if duplicate_key is not None:
                return None, f"Duplicate key in frontmatter: {duplicate_key}"
            loaded_frontmatter = loader.construct_document(node) if node is not None else None
        finally:
            loader.dispose()
    except (yaml.YAMLError, ValueError) as exc:
        return None, f"Invalid YAML in frontmatter: {exc}"

    return string_keyed_mapping(loaded_frontmatter, "Frontmatter")


def string_keyed_mapping(value: object, label: str) -> tuple[dict[str, object] | None, str]:
    """Return a YAML mapping with string keys or a field diagnostic."""
    if not isinstance(value, dict):
        return None, f"{label} must be a YAML dictionary"
    mapping = cast("dict[object, object]", value)
    non_string_keys = [key for key in mapping if not isinstance(key, str)]
    if non_string_keys:
        keys = ", ".join(repr(key) for key in non_string_keys)
        return None, f"{label} keys must be strings: {keys}"

    return {key: item for key, item in mapping.items() if isinstance(key, str)}, ""
