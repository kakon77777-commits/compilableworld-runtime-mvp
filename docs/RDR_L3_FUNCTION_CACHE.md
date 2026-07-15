# RDR L3 Function Cache

CompilableWorld 現在把論文 08 的低風險 RDR L3 提案落在 FunctionIR Registry，而不是把整個 Kernel 改造成黑盒派發器。

## Boundary

- 只有通過 `functions.json` schema、且 `purity: pure` 的 numeric FunctionIR 會進入 Registry。
- Cache key 是 `function_id`、function version 與完整 numeric input tuple。
- Cache 是每個 `FunctionRegistry` instance 的 bounded LRU，預設容量 2048；超過容量會淘汰最久未使用項目。
- Cache 不讀寫 StateStore、不產生 EventIR、不進 Snapshot；清空或重建都不會改變世界語義。

## Observability

`WorldRuntime.diagnostics()` 會回報：

```json
{
  "function_cache": {
    "hits": 1,
    "misses": 2,
    "evictions": 0,
    "size": 2,
    "capacity": 2048
  }
}
```

這個切片對應「同一條純規則被大量實體重用」的情境；階級門檻、狀態衰減、排程、SCC／拆環與自適應閘門仍未被宣稱已實作。
