---
title: "RGGD-09｜從方法論到 Runtime：RGGG 中間表示、生成循環與 MVP 路線"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部技術白皮書"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD-09｜RGGG Runtime 中間表示與 MVP 路線

## 0. 目標

本篇把前八篇收斂成：

$$
\boxed{
\text{RGGG Runtime}
}
$$

即 Recursive Generative Game Grammar Runtime。

最小循環：

$$
\boxed{
\text{Primitive DB}
\rightarrow
\text{Grammar}
\rightarrow
\text{Generator}
\rightarrow
\text{Validator}
\rightarrow
\text{World State}
\rightarrow
\text{History}
\rightarrow
\text{Grammar Update}
}
$$

## 1. Core Data Model

建議至少有：

```text
Primitive
Type
Constraint
Grammar
Recipe
Object
Relation
Event
History
Rule
Generator
ValidationResult
```

## 2. Primitive

```yaml
id:
type:
properties:
tags:
provenance:
```

## 3. Grammar

```yaml
grammar_id:
input_types:
output_type:
rules:
constraints:
parameters:
version:
```

## 4. Recipe

每個生成物保存：

```yaml
recipe_id:
grammar_version:
inputs:
seed:
choices:
history_context:
```

## 5. Generated Object

```yaml
object_id:
type:
recipe_id:
properties:
relations:
created_at:
created_by:
state:
```

## 6. Event

```yaml
event_id:
actors:
objects:
state_before:
action:
state_after:
causal_refs:
significance:
```

## 7. Grammar Mutation

```yaml
mutation:
  parent_grammar:
  trigger:
  proposed_rule:
  validation:
  status:
```

Candidate 不直接 Commit。

## 8. Runtime Loop

```text
observe world
→ select generation opportunity
→ build candidate
→ validate
→ commit object/event
→ update world state
→ record history
→ detect possible grammar update
→ validate grammar update
→ continue
```

## 9. Layered Architecture

### Layer 0 — Stable Runtime Core
State、Persistence、Validation、Versioning、Rollback。

### Layer 1 — Primitive / Type
Material、Body、Form、Action。

### Layer 2 — Domain Grammar
Item、Creature、Skill、Culture。

### Layer 3 — World Grammar
Economy、Ecology、Civilization、History。

### Layer 4 — Agent / AI Layer
Proposal、Planning、Interpretation、Narrative。

## 10. AI 不直接掌握 Canonical Truth

AI 只產生：

$$
\boxed{
\text{Proposal}
}
$$

Runtime 負責：

$$
\boxed{
\text{Validate}
\rightarrow
\text{Commit}
}
$$

## 11. 與 Composable Visual Runtime

介面：

$$
\text{Generated Object}
\rightarrow
\text{Visual Recipe}
$$

例如 Material → Material Layer、Culture → Style Grammar、Damage → Overlay、History → Unique Mark。

## 12. 與 Persistent Subject Runtime

角色：

$$
Subject
\rightarrow
Intent
\rightarrow
Action
\rightarrow
Event
\rightarrow
History
$$

又可以：

$$
History
\rightarrow
NewGoal
\rightarrow
NewGeneration.
$$

## 13. 與 AI-Composable Roguelike

Roguelike 可成為第一個完整產品應用案例之一。

可生成：World Archetype、Faction、Monster、Item、Class、Ability、Culture、Visual Identity。

但 RGGG Runtime 本身不得被鎖死在 Roguelike。

## 14. 第一個 MVP

不要做完整世界。

只做：

$$
\boxed{
\text{Material}
+
\text{Item}
+
\text{History}
}
$$

最小需求：

- 10 materials；
- 5 forms；
- 3 processes；
- 5 decorations；
- 3 damage states；
- 3 history event types。

## 15. MVP 生成流程

```text
Material
+ Form
+ Process
→ Item

Item
+ Use Event
→ Historical Item

Historical Item
→ Visual Recipe
```

## 16. MVP 驗收

至少：

1. 生成 100 個合法 Item；
2. 同 Seed 可重建；
3. Material Property 真正影響 Stats；
4. Process 真正改變成品；
5. History 真正改變 Value / Identity；
6. Invalid Combination 被攔截；
7. 每個 Object 有 Recipe；
8. 每個 Event 有 Lineage；
9. 可輸出 Visual Recipe；
10. 可批次測試。

## 17. 第二階段

加入 Creature Grammar：

$$
\text{Body}
+
\text{Tissue}
+
\text{Locomotion}
+
\text{Ecology}
$$

並驗證 Functional Coherence。

## 18. 第三階段

加入 Culture / Technology Grammar：

$$
\text{History}
\rightarrow
\text{New Rule}
\rightarrow
\text{Grammar Update}
$$

這時才真正進入強 RGGD。

## 19. 第四階段

加入 Persistent Subject：Agent Invention、Organization、Institutional Creation、Technology Diffusion。

## 20. 版本控制

所有 Grammar 變更要有：

```yaml
version:
parent_version:
migration:
validation:
rollback:
```

避免長期世界不可回復。

## 21. Benchmark

RGGG 可建立：

- valid-generation rate；
- unique-mechanic rate；
- causal propagation depth；
- historical reuse rate；
- grammar mutation success；
- invalid-generation rejection；
- replay determinism。

## 22. 不是追求最大世界

第一個產品不需要無限物種、無限文明、無限科技。

真正目標是證明：

$$
\boxed{
\text{Finite Grammar}
\rightarrow
\text{High Meaningful Generative Density}
}
$$

## 23. 最終架構

長期：

$$
\boxed{
\text{RGGG}
+
\text{Composable Visual Runtime}
+
\text{Persistent Subject Runtime}
+
\text{World State Runtime}
}
$$

可形成統一的 AI-era game world substrate。

## 24. 一句話總結

> **RGGG Runtime 的工程目標，是把 Primitive、Type、Constraint、Grammar、Recipe、Event、History 與 Grammar Mutation 全部變成可版本化、可驗證、可重播的結構，使生成世界不靠無限手工內容，而靠可持續演化的合法生成語法。**
