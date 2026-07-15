"""Restricted FunctionIR and deterministic function registry.

FunctionIR is intentionally an expression tree, not Python source.  Only
numeric pure functions are admitted in v0.1; side effects remain the domain
of Runtime Modules and their StateDelta/EventIR contracts.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any


FUNCTION_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
INPUT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
FUNCTION_OPS = {"add", "sub", "mul", "div", "min", "max", "neg", "clamp", "round"}
FUNCTION_TYPES = {"number"}


class FunctionDefinitionError(ValueError):
    pass


class FunctionRegistryError(RuntimeError):
    pass


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_expression(expression: Any, input_names: set[str], label: str) -> None:
    if _number(expression):
        return
    if not isinstance(expression, dict):
        raise FunctionDefinitionError(f"{label} 必須是數字或 expression object")
    unknown = set(expression) - {"ref", "const", "op", "args"}
    if unknown:
        raise FunctionDefinitionError(f"{label} 含未知欄位: {sorted(unknown)}")
    if "ref" in expression:
        if set(expression) != {"ref"} or not isinstance(expression["ref"], str) or expression["ref"] not in input_names:
            raise FunctionDefinitionError(f"{label}.ref 必須引用已宣告輸入")
        return
    if "const" in expression:
        if set(expression) != {"const"} or not _number(expression["const"]):
            raise FunctionDefinitionError(f"{label}.const 必須是數字")
        return
    if set(expression) != {"op", "args"}:
        raise FunctionDefinitionError(f"{label} 必須包含 op 與 args")
    op = expression["op"]
    args = expression["args"]
    if op not in FUNCTION_OPS:
        raise FunctionDefinitionError(f"{label}.op 不支援: {op}")
    if not isinstance(args, list):
        raise FunctionDefinitionError(f"{label}.args 必須是陣列")
    arity = {
        "add": (2, None), "sub": (2, 2), "mul": (2, None), "div": (2, 2),
        "min": (1, None), "max": (1, None), "neg": (1, 1), "clamp": (3, 3),
        "round": (1, 1),
    }[op]
    minimum, maximum = arity
    if len(args) < minimum or (maximum is not None and len(args) != maximum):
        expected = str(minimum) if maximum == minimum else f"至少 {minimum}"
        raise FunctionDefinitionError(f"{label}.args 數量錯誤，需要 {expected}")
    for index, child in enumerate(args):
        _validate_expression(child, input_names, f"{label}.args[{index}]")


def validate_function_source(source: Any) -> dict[str, list[dict[str, Any]]]:
    """Validate and normalize a ``functions.json`` document."""
    if not isinstance(source, dict):
        raise FunctionDefinitionError("functions.json 必須是物件")
    unknown = set(source) - {"functions"}
    if unknown:
        raise FunctionDefinitionError(f"functions.json 含未知欄位: {sorted(unknown)}")
    entries = source.get("functions", [])
    if not isinstance(entries, list):
        raise FunctionDefinitionError("functions.functions 必須是陣列")

    normalized: list[dict[str, Any]] = []
    function_ids: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"functions.json.functions[{index}]"
        if not isinstance(entry, dict):
            raise FunctionDefinitionError(f"{label} 必須是物件")
        allowed = {"function_id", "version", "purity", "inputs", "output", "expression"}
        unknown_entry = set(entry) - allowed
        required = allowed
        if unknown_entry:
            raise FunctionDefinitionError(f"{label} 含未知欄位: {sorted(unknown_entry)}")
        if set(entry) != required:
            raise FunctionDefinitionError(f"{label} 必須剛好包含: {sorted(required)}")
        function_id = entry["function_id"]
        version = entry["version"]
        purity = entry["purity"]
        inputs = entry["inputs"]
        output = entry["output"]
        if not isinstance(function_id, str) or not FUNCTION_ID_RE.match(function_id):
            raise FunctionDefinitionError(f"{label}.function_id 不合法")
        if function_id in function_ids:
            raise FunctionDefinitionError(f"functions.json 含重複 function_id: {function_id}")
        function_ids.add(function_id)
        if not isinstance(version, str) or not version.strip():
            raise FunctionDefinitionError(f"{label}.version 必須是非空字串")
        if purity != "pure":
            raise FunctionDefinitionError(f"{label}.purity 目前只能是 pure")
        if not isinstance(inputs, dict) or not inputs:
            raise FunctionDefinitionError(f"{label}.inputs 必須是非空物件")
        input_types: dict[str, str] = {}
        for name, type_name in inputs.items():
            if not isinstance(name, str) or not INPUT_NAME_RE.match(name):
                raise FunctionDefinitionError(f"{label}.inputs 含不合法名稱: {name}")
            if type_name not in FUNCTION_TYPES:
                raise FunctionDefinitionError(f"{label}.inputs.{name} 不支援型別: {type_name}")
            input_types[name] = type_name
        if output not in FUNCTION_TYPES:
            raise FunctionDefinitionError(f"{label}.output 不支援型別: {output}")
        _validate_expression(entry["expression"], set(input_types), f"{label}.expression")
        normalized.append({
            "function_id": function_id,
            "version": version,
            "purity": purity,
            "inputs": input_types,
            "output": output,
            "expression": entry["expression"],
        })
    return {"functions": normalized}


def _evaluate_expression(expression: Any, values: dict[str, float]) -> float | int:
    if _number(expression):
        return expression
    if "ref" in expression:
        return values[expression["ref"]]
    if "const" in expression:
        return expression["const"]
    op = expression["op"]
    args = [_evaluate_expression(child, values) for child in expression["args"]]
    if op == "add":
        return sum(args)
    if op == "sub":
        return args[0] - args[1]
    if op == "mul":
        result: float | int = 1
        for value in args:
            result *= value
        return result
    if op == "div":
        if args[1] == 0:
            raise FunctionRegistryError("FunctionIR 除以零")
        return args[0] / args[1]
    if op == "min":
        return min(args)
    if op == "max":
        return max(args)
    if op == "neg":
        return -args[0]
    if op == "round":
        return round(args[0])
    if op == "clamp":
        value, minimum, maximum = args
        if minimum > maximum:
            raise FunctionRegistryError("FunctionIR clamp 的 minimum 不可大於 maximum")
        return min(maximum, max(minimum, value))
    raise FunctionRegistryError(f"FunctionIR 不支援 op: {op}")


class FunctionRegistry:
    def __init__(self, source: dict[str, Any] | None = None, max_cache_entries: int = 2048) -> None:
        if isinstance(max_cache_entries, bool) or not isinstance(max_cache_entries, int) or max_cache_entries < 1:
            raise ValueError("FunctionIR cache capacity must be a positive integer")
        normalized = validate_function_source(source or {"functions": []})
        self._functions = {item["function_id"]: item for item in normalized["functions"]}
        self._max_cache_entries = max_cache_entries
        self._cache: OrderedDict[tuple[str, str, tuple[tuple[str, int | float], ...]], int | float] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0

    @classmethod
    def from_package(cls, package: dict[str, Any]) -> "FunctionRegistry":
        return cls(package.get("functions", {"functions": []}))

    def evaluate(self, function_id: str, values: dict[str, Any]) -> float | int:
        try:
            function = self._functions[function_id]
        except KeyError as exc:
            raise FunctionRegistryError(f"未知 FunctionIR: {function_id}") from exc
        if not isinstance(values, dict):
            raise FunctionRegistryError("FunctionIR 輸入必須是物件")
        expected_inputs = set(function["inputs"])
        if set(values) != expected_inputs:
            missing = sorted(expected_inputs - set(values))
            extra = sorted(set(values) - expected_inputs)
            raise FunctionRegistryError(f"FunctionIR 輸入不匹配: missing={missing}, extra={extra}")
        if any(not _number(value) for value in values.values()):
            raise FunctionRegistryError("FunctionIR number 輸入不可是 bool 或非數字")
        cache_key = (function_id, function["version"], tuple(sorted(values.items())))
        if cache_key in self._cache:
            result = self._cache.pop(cache_key)
            self._cache[cache_key] = result
            self._cache_hits += 1
            return result
        self._cache_misses += 1
        result = _evaluate_expression(function["expression"], values)
        if len(self._cache) >= self._max_cache_entries:
            self._cache.popitem(last=False)
            self._cache_evictions += 1
        self._cache[cache_key] = result
        return result

    def has(self, function_id: str) -> bool:
        """Return whether a package declared this function explicitly."""
        return function_id in self._functions

    def cache_stats(self) -> dict[str, int]:
        """Return bounded-cache metrics for RDR observability."""
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "evictions": self._cache_evictions,
            "size": len(self._cache),
            "capacity": self._max_cache_entries,
        }

    def clear_cache(self) -> None:
        """Clear derived memoized values and reset their counters."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_evictions = 0

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "function_id": function_id,
                "version": function["version"],
                "purity": function["purity"],
                "inputs": dict(function["inputs"]),
                "output": function["output"],
            }
            for function_id, function in sorted(self._functions.items())
        ]


__all__ = [
    "FunctionDefinitionError", "FunctionRegistry", "FunctionRegistryError",
    "validate_function_source",
]
