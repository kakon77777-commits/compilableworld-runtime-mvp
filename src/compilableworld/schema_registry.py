"""Versioned JSON Schema contracts shared by Authoring, Compiler, and Studio.

The schemas are repository-level artifacts under ``schemas/`` so editors can
consume them without importing the runtime.  This module adds a tiny,
dependency-free discovery layer and verifies that the checked-in documents
match the IDs emitted into compiled Runtime Packages.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_CATALOG_FORMAT = "compilableworld.schema-catalog/v0.1"

_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"
_SCHEMAS: dict[str, dict[str, str]] = {
    "action_behaviors": {
        "schema_id": "compilableworld.schema/action-behaviors/v0.7",
        "filename": "action-behaviors.v0.7.schema.json",
        "version": "v0.7",
        "kind": "json",
    },
    "functions": {
        "schema_id": "compilableworld.schema/functions/v0.1",
        "filename": "functions.v0.1.schema.json",
        "version": "v0.1",
        "kind": "json",
    },
    "scenarios": {
        "schema_id": "compilableworld.schema/scenarios/v0.1",
        "filename": "scenarios.v0.1.schema.json",
        "version": "v0.1",
        "kind": "json",
    },
    "state_machines": {
        "schema_id": "compilableworld.schema/state-machines/v0.6",
        "filename": "state-machines.v0.6.schema.json",
        "version": "v0.6",
        "kind": "json",
    },
    "runtime_package": {
        "schema_id": "compilableworld.schema/runtime-package/v0.1",
        "filename": "runtime-package.v0.1.schema.json",
        "version": "v0.1",
        "kind": "json",
    },
    "rooms": {
        "schema_id": "compilableworld.schema/csv/rooms/v0.1",
        "filename": "rooms.v0.1.csv.schema.json",
        "version": "v0.1",
        "kind": "csv",
    },
    "exits": {
        "schema_id": "compilableworld.schema/csv/exits/v0.1",
        "filename": "exits.v0.1.csv.schema.json",
        "version": "v0.1",
        "kind": "csv",
    },
    "entities": {
        "schema_id": "compilableworld.schema/csv/entities/v0.1",
        "filename": "entities.v0.1.csv.schema.json",
        "version": "v0.1",
        "kind": "csv",
    },
    "items": {
        "schema_id": "compilableworld.schema/csv/items/v0.1",
        "filename": "items.v0.1.csv.schema.json",
        "version": "v0.1",
        "kind": "csv",
    },
    "studio_world_ir": {
        "schema_id": "compilableworld.schema/studio-world-ir/v0.1",
        "filename": "studio-world-ir.v0.1.schema.json",
        "version": "v0.1",
        "kind": "json",
    },
    "studio_mapping": {
        "schema_id": "compilableworld.schema/studio-mapping/v0.1",
        "filename": "studio-mapping.v0.1.schema.json",
        "version": "v0.1",
        "kind": "json",
    },
}

_OPTIONAL_SCHEMAS: dict[str, dict[str, str]] = {
    "object_reentry": {
        "schema_id": "compilableworld.schema/object-reentry/v0.1",
        "filename": "object-reentry.v0.1.schema.json", "version": "v0.1", "kind": "json",
    },
}


class SchemaContractError(ValueError):
    """Raised when a checked-in schema contract is missing or inconsistent."""


def _selected_schemas(include: tuple[str, ...]) -> dict[str, dict[str, str]]:
    selected = dict(_SCHEMAS)
    for key in include:
        if key not in _OPTIONAL_SCHEMAS:
            raise SchemaContractError(f"unknown optional schema: {key}")
        selected[key] = _OPTIONAL_SCHEMAS[key]
    return selected


def schema_contracts(*, verify: bool = False, include: tuple[str, ...] = ()) -> dict[str, str]:
    """Return stable package-field to JSON-Schema-ID mappings.

    ``verify=True`` is used by the compiler and tests.  Keeping verification
    opt-in lets lightweight tooling inspect the mapping even while packaging
    metadata is being assembled.
    """
    selected = _selected_schemas(include)
    if verify:
        for key, metadata in selected.items():
            path = _SCHEMA_ROOT / metadata["filename"]
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SchemaContractError(f"schema contract unavailable: {path}") from exc
            if document.get("$id") != metadata["schema_id"]:
                raise SchemaContractError(
                    f"schema contract ID mismatch for {key}: {document.get('$id')}"
                )
    return {key: metadata["schema_id"] for key, metadata in selected.items()}


def schema_document(key: str) -> dict[str, Any]:
    """Load one checked-in schema document by its package/source key."""
    try:
        metadata = {**_SCHEMAS, **_OPTIONAL_SCHEMAS}[key]
    except KeyError as exc:
        raise SchemaContractError(f"unknown schema contract: {key}") from exc
    path = _SCHEMA_ROOT / metadata["filename"]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaContractError(f"schema contract unavailable: {path}") from exc
    if not isinstance(document, dict) or document.get("$id") != metadata["schema_id"]:
        raise SchemaContractError(f"schema contract ID mismatch for {key}")
    return document


def csv_schema_columns(key: str) -> list[dict[str, Any]]:
    """Return the declared CSV columns for Compiler header validation."""
    metadata = _SCHEMAS.get(key)
    if not metadata or metadata.get("kind") != "csv":
        raise SchemaContractError(f"not a CSV schema contract: {key}")
    document = schema_document(key)
    csv_metadata = document.get("x-csv")
    columns = csv_metadata.get("columns") if isinstance(csv_metadata, dict) else None
    if not isinstance(columns, list) or any(not isinstance(column, dict) for column in columns):
        raise SchemaContractError(f"CSV schema columns invalid: {key}")
    return [dict(column) for column in columns]


def schema_catalog(*, include: tuple[str, ...] = ()) -> dict[str, Any]:
    """Return read-only schema metadata suitable for Studio discovery."""
    records: list[dict[str, Any]] = []
    for key, metadata in _selected_schemas(include).items():
        path = _SCHEMA_ROOT / metadata["filename"]
        record: dict[str, Any] = {
            "key": key,
            "schema_id": metadata["schema_id"],
            "version": metadata["version"],
            "filename": metadata["filename"],
            "kind": metadata["kind"],
            "available": path.is_file(),
        }
        if path.is_file():
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                document = {}
            if isinstance(document, dict) and isinstance(document.get("title"), str):
                record["title"] = document["title"]
        records.append(record)
    return {
        "format": SCHEMA_CATALOG_FORMAT,
        "read_only": True,
        "schemas": records,
    }


__all__ = [
    "SCHEMA_CATALOG_FORMAT", "SchemaContractError", "csv_schema_columns",
    "schema_catalog", "schema_contracts", "schema_document",
]
