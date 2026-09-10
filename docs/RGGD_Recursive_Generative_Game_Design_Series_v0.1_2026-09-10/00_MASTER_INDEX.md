---
title: "RGGD — 遞迴生成式遊戲設計方法論｜Master Index"
english_title: "Recursive Generative Game Design"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部研究系列總索引"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD — Recursive Generative Game Design
## 遞迴生成式遊戲設計方法論

## 0. 系列定位

RGGD 不是單純的程序生成（PCG）、生成式 AI 遊戲、沙盒遊戲或動態世界模擬。

它研究的是：

> 如何用有限的 Primitive、Type、Constraint、Grammar 與 Runtime，建立一個能持續產生合法物件、關係、狀態、歷史、主體，甚至新規則與新 Grammar 的遊戲系統。

核心不是：

$$
\text{Developer}
\rightarrow
\text{Handcraft More Content}
$$

而是：

$$
\boxed{
\text{Developer}
\rightarrow
\text{Design Generative Conditions}
\rightarrow
\text{World Produces Valid Structure}
}
$$

其中 **RGGG — Recursive Generative Game Grammar** 是 RGGD 的形式／Runtime 核心。

## 1. 系列結構

### Part I：生成本體

1. `RGGD-01_從內容列舉到生成語法.md`
2. `RGGD-02_Primitive_Type與Constraint.md`
3. `RGGD-03_階層式組合與生成閉包.md`
4. `RGGD-04_遞迴回流與動態Grammar.md`

### Part II：遊戲世界

5. `RGGD-05_生成式物件世界.md`
6. `RGGD-06_歷史回流與生成世界史.md`
7. `RGGD-07_主體與文明作為生成器.md`

### Part III：驗證與 Runtime

8. `RGGD-08_組合爆炸品質控制與驗證.md`
9. `RGGD-09_RGGG_Runtime中間表示與MVP路線.md`

## 2. 形式核心

RGGD 的最小循環：

$$
X_{n+1}
=
\mathcal G_n
(
X_n,
C_n,
H_n,
E_n
)
$$

其中：

- $X_n$：目前可用物件／狀態／規則；
- $\mathcal G_n$：當前生成 Grammar；
- $C_n$：Constraint；
- $H_n$：History；
- $E_n$：Environment。

關鍵在於：

$$
\boxed{
X_{n+1}
\neq
\text{Final Output Only}
}
$$

生成結果可以重新成為：

- Primitive；
- Type；
- Relation；
- Rule；
- Operator；
- Grammar；
- Historical Constraint。

因此：

$$
\boxed{
(\mathcal G_n,X_n)
\rightarrow
X_{n+1}
\rightarrow
\mathcal G_{n+1}
\rightarrow
X_{n+2}
\rightarrow
\cdots
}
$$

## 3. 與既有研究的關係

本系列承接但不等同於既有研究中的：

- Dynamic Generator Grammar；
- Compositional Closure；
- Meta-Generation；
- Ontology Change；
- Recursive Frontier Renewal；
- Grammar-Generative Tension；
- Constraint as Condition of Stable Generation；
- Rule → HistoryFamily；
- Rule → Subjects → NewRules；
- Persistent Consequence；
- Semantic Causality；
- Composable Semantic Grammars。

RGGD 的新增工作，是把這些原本分散於數學、認知方法論、持久世界、生成理論與個別遊戲專案的概念，第一次收束成**可用於設計一般遊戲的工程方法論**。

## 4. 系列硬規則

1. 生成不等於隨機。
2. 組合不等於笛卡兒積。
3. Constraint 是生成品質的條件，不只是限制。
4. 生成結果可以重新進入生成系統。
5. 歷史必須反過來改變未來生成。
6. 主體可以成為新的生成器。
7. AI 不是必要條件；沒有 LLM 仍可實作 RGGD。
8. AI 適合擴展、解讀、搜尋與驗證，不應取代所有 deterministic rule。
9. Generated 不等於 Valid。
10. Generated 不等於 Interesting。
11. Runtime 必須能追蹤 provenance、state transition 與 failure。
12. 真正目標是 Meaningful Generative Density，而不是最大組合數。

## 5. 一句話定位

> **RGGD 的目的，不是讓遊戲「內容很多」，而是讓遊戲擁有一套能把有限構件反覆組合、封裝、歷史化並重新投入生成的世界語法，使內容、歷史與規則能在可驗證邊界內持續增生。**
