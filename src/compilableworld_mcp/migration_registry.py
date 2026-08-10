"""Versioned, explicit migration chains for MCP/runtime boundary payloads."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .contracts import MCPWorldError


MCP_MIGRATION_CONTRACT = "compilableworld.mcp-migration/v0.1"
MigrationTransform = Callable[[dict[str, Any]], dict[str, Any]]


class MigrationRegistryError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = MCP_MIGRATION_CONTRACT
        return payload


def _required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise MigrationRegistryError("INVALID_MIGRATION", f"{field_name} must be non-empty")
    return normalized


@dataclass(frozen=True, slots=True)
class MigrationStep:
    kind: str
    from_version: str
    to_version: str
    name: str
    transform: MigrationTransform

    def safe_metadata(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "name": self.name,
        }

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            migrated = self.transform(deepcopy(payload))
        except MigrationRegistryError:
            raise
        except Exception as exc:
            raise MigrationRegistryError(
                "MIGRATION_FAILED",
                f"migration step failed: {self.name}",
            ) from exc
        if not isinstance(migrated, dict):
            raise MigrationRegistryError(
                "MIGRATION_INVALID_RESULT",
                f"migration step must return an object: {self.name}",
            )
        return migrated


class MigrationRegistry:
    """Registry of named, explicit migration steps with deterministic paths."""

    def __init__(self) -> None:
        self._steps: dict[tuple[str, str, str], MigrationStep] = {}

    def register(
        self,
        kind: str,
        from_version: str,
        to_version: str,
        transform: MigrationTransform,
        *,
        name: str | None = None,
    ) -> MigrationStep:
        normalized_kind = _required(kind, "kind")
        source = _required(from_version, "from_version")
        target = _required(to_version, "to_version")
        if source == target:
            raise MigrationRegistryError("INVALID_MIGRATION", "migration versions must differ")
        if not callable(transform):
            raise MigrationRegistryError("INVALID_MIGRATION", "migration transform must be callable")
        step = MigrationStep(
            normalized_kind,
            source,
            target,
            _required(name or f"{normalized_kind}:{source}->{target}", "name"),
            transform,
        )
        key = (normalized_kind, source, target)
        if key in self._steps:
            raise MigrationRegistryError("MIGRATION_CONFLICT", f"migration already registered: {key}")
        self._steps[key] = step
        return step

    def available(self, kind: str) -> list[dict[str, str]]:
        normalized_kind = _required(kind, "kind")
        return [
            step.safe_metadata()
            for step in sorted(
                self._steps.values(),
                key=lambda item: (item.kind, item.from_version, item.to_version),
            )
            if step.kind == normalized_kind
        ]

    def find_path(self, kind: str, from_version: str, to_version: str) -> list[MigrationStep]:
        normalized_kind = _required(kind, "kind")
        source = _required(from_version, "from_version")
        target = _required(to_version, "to_version")
        if source == target:
            return []

        queue: deque[tuple[str, list[MigrationStep]]] = deque([(source, [])])
        visited = {source}
        while queue:
            current, path = queue.popleft()
            for step in sorted(
                self._steps.values(),
                key=lambda item: (item.from_version, item.to_version, item.name),
            ):
                if step.kind != normalized_kind or step.from_version != current:
                    continue
                next_path = [*path, step]
                if step.to_version == target:
                    return next_path
                if step.to_version not in visited:
                    visited.add(step.to_version)
                    queue.append((step.to_version, next_path))
        raise MigrationRegistryError(
            "MIGRATION_NOT_FOUND",
            f"no migration path for {normalized_kind}: {source} -> {target}",
        )

    def migrate(
        self,
        payload: Mapping[str, Any],
        *,
        kind: str,
        from_version: str,
        to_version: str,
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise MigrationRegistryError("INVALID_MIGRATION", "migration payload must be an object")
        migrated = deepcopy(dict(payload))
        for step in self.find_path(kind, from_version, to_version):
            migrated = step.apply(migrated)
        return migrated


__all__ = [
    "MCP_MIGRATION_CONTRACT",
    "MigrationRegistry",
    "MigrationRegistryError",
    "MigrationStep",
]
