"""Small deterministic validator for review-graph's published JSON schemas."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class SchemaDiagnostic:
    """One field-level schema failure with a stable JSON path."""

    path: str
    code: str
    message: str
    accepted_shape: str
    accepted_values: tuple[object, ...] = ()


class SchemaValidationError(ValueError):
    """Aggregate every structural diagnostic from one schema boundary."""

    def __init__(self, schema_id: str, diagnostics: tuple[SchemaDiagnostic, ...]) -> None:
        """Render all diagnostics without dropping field-level detail."""
        self.schema_id = schema_id
        self.diagnostics = diagnostics
        rendered = "; ".join(
            f"{item.path}: {item.message} (accepted shape: {item.accepted_shape}"
            + (f"; accepted values: {', '.join(repr(value) for value in item.accepted_values)}" if item.accepted_values else "")
            + ")"
            for item in diagnostics
        )
        super().__init__(f"schema {schema_id} rejected {len(diagnostics)} field(s): {rendered}")

    def as_dict(self) -> dict[str, object]:
        """Return deterministic diagnostics suitable for a constrained retry."""
        return {
            "diagnostics": [
                {
                    "accepted_shape": item.accepted_shape,
                    "accepted_values": list(item.accepted_values),
                    "code": item.code,
                    "message": item.message,
                    "path": item.path,
                }
                for item in self.diagnostics
            ],
            "schema_id": self.schema_id,
        }


def _resolve_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        msg = f"only local schema references are supported: {reference}"
        raise ValueError(msg)
    current: object = root
    for token in reference.removeprefix("#/").split("/"):
        if not isinstance(current, dict) or token not in current:
            msg = f"schema reference does not resolve: {reference}"
            raise ValueError(msg)
        current = current[token]
    if not isinstance(current, dict):
        msg = f"schema reference is not an object: {reference}"
        raise TypeError(msg)
    return current


def _type_name(value: object) -> str:  # noqa: PLR0911
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _accepted_types(schema: dict[str, Any]) -> tuple[str, ...]:
    raw = schema.get("type")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return tuple(item for item in raw if isinstance(item, str))
    return ()


def _matches_type(value: object, accepted: tuple[str, ...]) -> bool:
    observed = _type_name(value)
    return observed in accepted or (observed == "integer" and "number" in accepted)


def _shape(schema: dict[str, Any]) -> str:
    accepted = _accepted_types(schema)
    if accepted:
        return " | ".join(accepted)
    if "const" in schema:
        return f"constant {schema['const']!r}"
    if "enum" in schema:
        return "enumerated value"
    return "value described by schema"


def _diagnose(value: object, schema: dict[str, Any], root: dict[str, Any], path: str, output: list[SchemaDiagnostic]) -> None:  # noqa: C901, PLR0912
    reference = schema.get("$ref")
    if isinstance(reference, str):
        _diagnose(value, _resolve_ref(root, reference), root, path, output)
        return
    accepted = _accepted_types(schema)
    if accepted and not _matches_type(value, accepted):
        output.append(SchemaDiagnostic(path, "type", f"observed {_type_name(value)}", _shape(schema), accepted))
        return
    if "const" in schema and (_type_name(value) != _type_name(schema["const"]) or value != schema["const"]):
        expected = schema["const"]
        output.append(SchemaDiagnostic(path, "const", f"must equal {expected!r}", _shape(schema), (expected,)))
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        output.append(SchemaDiagnostic(path, "enum", f"unknown value {value!r}", _shape(schema), tuple(enum)))
    pattern = schema.get("pattern")
    if isinstance(value, str) and isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
        output.append(SchemaDiagnostic(path, "pattern", f"does not match {pattern}", f"string matching {pattern}"))
    minimum = schema.get("minimum")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isinstance(minimum, (int, float)) and value < minimum:
        output.append(SchemaDiagnostic(path, "minimum", f"must be at least {minimum}", f"number >= {minimum}"))
    min_length = schema.get("minLength")
    if isinstance(value, str) and isinstance(min_length, int) and len(value) < min_length:
        output.append(SchemaDiagnostic(path, "minLength", f"must contain at least {min_length} character(s)", f"string length >= {min_length}"))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        required = schema.get("required", [])
        if isinstance(required, list):
            for name in required:
                if isinstance(name, str) and name not in value:
                    child_schema = properties.get(name, {})
                    child = child_schema if isinstance(child_schema, dict) else {}
                    output.append(SchemaDiagnostic(f"{path}.{name}", "required", "missing required field", _shape(child)))
        additional = schema.get("additionalProperties", True)
        if additional is False:
            output.extend(
                SchemaDiagnostic(f"{path}.{name}", "unknown", "unknown field", "field declared by this schema") for name in sorted(set(value) - set(properties))
            )
        for name, child_value in value.items():
            child_schema = properties.get(name)
            if isinstance(child_schema, dict):
                _diagnose(child_value, child_schema, root, f"{path}.{name}", output)
            elif isinstance(additional, dict):
                _diagnose(child_value, additional, root, f"{path}.{name}", output)
    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            output.append(SchemaDiagnostic(path, "minItems", f"must contain at least {min_items} item(s)", f"array length >= {min_items}"))
        if isinstance(max_items, int) and len(value) > max_items:
            output.append(SchemaDiagnostic(path, "maxItems", f"must contain at most {max_items} item(s)", f"array length <= {max_items}"))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _diagnose(item, item_schema, root, f"{path}[{index}]", output)


def load_schema(path: Path) -> dict[str, Any]:
    """Load one checked-in schema object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        msg = f"schema root must be an object: {path}"
        raise TypeError(msg)
    return value


def schema_diagnostics(value: object, schema: dict[str, Any]) -> tuple[SchemaDiagnostic, ...]:
    """Return every supported structural failure in stable path order."""
    output: list[SchemaDiagnostic] = []
    _diagnose(value, schema, schema, "$", output)
    return tuple(sorted(output, key=lambda item: (item.path, item.code, item.message)))


def require_schema(value: object, schema_path: Path) -> None:
    """Raise one aggregate error when a published schema rejects a value."""
    schema = load_schema(schema_path)
    diagnostics = schema_diagnostics(value, schema)
    if diagnostics:
        raise SchemaValidationError(str(schema.get("$id", schema_path)), diagnostics)
