---
title: "RGGD-06｜歷史回流：從生成內容到生成世界史"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部方法論論文"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD-06｜歷史回流與生成世界史

## 0. 核心問題

隨機生成一個世界，不等於世界會產生歷史。

真正的歷史要求：

$$
\boxed{
\text{Past Event}
\rightarrow
\text{Persistent Consequence}
\rightarrow
\text{Future Constraint}
}
$$

如果昨天發生的事對今天沒有因果影響，那只是 transient content。

## 1. Event

事件不是純 log。

定義：

$$
e_t
=
(
actors,
state\_before,
action,
state\_after,
cause,
effects
).
$$

## 2. History

歷史：

$$
H_t
=
\{e_0,e_1,\ldots,e_t\}.
$$

但不能每次把完整 log 全讀一遍。需要 Event Log、Derived State、Semantic Memory 與 Provenance。

## 3. Historical Dependence

若：

$$
W_{t+1}=F(W_t,e_t)
$$

且後續 $W_{t+k}$ 仍受 $e_t$ 的可追溯影響，才形成真正歷史依賴。

## 4. 歷史改變 Grammar

例如：

- 戰爭解鎖新武器；
- 災難禁止某種建築；
- 宗教改革改變技能合法性；
- 王朝更替改變服裝 Grammar。

因此：

$$
\boxed{
H_t
\rightarrow
\Gamma_{t+1}
}
$$

## 5. 物件歷史

物品可以記錄 Creator、Owners、Battles、Repairs、Damage、Theft、Inheritance。

這些歷史可改變：

- value；
- reputation；
- ability；
- quest relevance；
- visual identity。

## 6. 人物歷史

角色狀態 $S_i(t)$ 不只由當前 Stats 決定，也受 Commitments、Betrayals、Trauma、Achievements、Relationships 影響。

## 7. 城市歷史

城市不是只有：

```text
city_level = 4
```

而可以有：曾被焚毀、曾被佔領、曾發生瘟疫、曾是宗教中心、曾生產傳奇武器。

這些歷史可改變 Architecture、Population、Politics、Quest、Culture。

## 8. History Compression

世界長期運行後，需要：

$$
\boxed{
\text{Event Log}
+
\text{Derived State}
+
\text{Compressed Memory}
}
$$

而不是只留一份巨大文字史。

## 9. Significant Event

不是所有小事件都升格。

可定義：

$$
Sig(e)
=
f(
rarity,
impact,
duration,
actors,
future\_effects
).
$$

只有：

$$
Sig(e)>\tau
$$

才成為重要歷史節點。

## 10. Emergent Narrative

敘事可以建立在真實狀態上：

$$
\boxed{
\text{Simulation}
\rightarrow
\text{History}
\rightarrow
\text{Narrative Rendering}
}
$$

AI 很適合把歷史轉成傳記、城市史、戰爭摘要、傳說，但不能反過來偽造未發生事件。

## 11. 生成世界史 vs 隨機 Flavor

隨機 Flavor：

> 這把劍據說殺過巨龍。

生成歷史：

> 系統真的記錄它在 Year 143 被角色 A 用來殺死 Dragon-17。

兩者完全不同。

## 12. Historical Re-entry

歷史必須能重新進入 Quest、Relationship、Politics、Economy、Grammar、Visual State。

例如：

$$
BattleScar
\rightarrow
VisualOverlay.
$$

## 13. Player Switching

若玩家從 A 切到 B：

$$
P_t=A
\rightarrow
P_{t+1}=B
$$

A 的歷史仍繼續。這使多主體世界真正連續。

## 14. Historical Causality Test

對任何宣稱「世界記得」的系統，應問：

> 若刪除某事件 $e_t$，今天世界狀態是否可觀察地不同？

如果答案永遠是否，則該事件只是 decoration log。

## 15. 一句話總結

> **RGGD 的世界史不是裝飾文字，而是會重新進入生成系統的 Causal Memory：事件改變狀態，狀態形成歷史，歷史再改變未來物件、規則、文化、主體與可能空間。**
