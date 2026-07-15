"""Read-only capture adapters for systems that own their own execution truth."""

from .compilableworld import CompilableWorldMemoryAdapter
from .phosphor import PhosphorTraceAdapter

__all__ = ["CompilableWorldMemoryAdapter", "PhosphorTraceAdapter"]
