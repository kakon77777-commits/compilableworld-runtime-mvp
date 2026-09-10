---
title: "RGGD-01｜從內容列舉到生成語法：遞迴生成式遊戲設計總論"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部方法論論文"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD-01｜從內容列舉到生成語法

## 0. 母問題

傳統大型遊戲往往透過增加更多怪物、物品、任務、職業、對話、地圖與劇情來增加內容量。其基本模型可寫成：

$$
\mathcal C=\{c_1,c_2,\ldots,c_N\}.
$$

當 $N$ 增加，內容增加，但成本也通常近似：

$$
Cost_{\mathrm{content}}\propto N.
$$

RGGD 要問的不是「如何更快地手工增加 $N$」，而是：**能不能改變內容本身的生產模型？**

## 1. Content Catalog 模式

Content Catalog 的優點是好控制、好測試、美術可精雕、敘事可精確安排；但它的長期限制是：

$$
\boxed{
\text{Content Growth}
\approx
\text{Authoring Growth}
}
$$

要增加 1000 個物件，通常仍要建立大量新定義、資產與測試。

## 2. Generative Grammar 模式

RGGD 改用：

$$
\boxed{
\text{Primitive}
+
\text{Grammar}
+
\text{Constraint}
+
\text{History}
}
$$

來生成內容：

$$
X=\mathcal G(P,C,H,E).
$$

其中 $P$ 為 Primitive，$C$ 為 Constraint，$H$ 為 History，$E$ 為 Environment，$\mathcal G$ 為生成 Grammar。

因此內容不再是一份固定清單，而是：

$$
\boxed{
\Omega_{\mathrm{valid}}
=
\{x\mid x\text{ can be legally generated}\}
}
$$

## 3. RGGD 不等於一般 PCG

傳統 PCG 常處理地圖、dungeon、encounter、loot、terrain。RGGD 更強調：

- 組合有型別與語義；
- 生成結果可再次成為生成輸入；
- 歷史會改變未來生成條件；
- 主體可以產生新的規則與生成器；
- Grammar 本身可以演化。

所以：

$$
\boxed{
\text{RGGD}
\supsetneq
\text{One-Shot Procedural Generation}
}
$$

## 4. RGGD 不等於生成式 AI

即使完全不使用 LLM，deterministic crafting grammar、typed creature grammar、procedural culture evolution、rule-generated quest graph、historical item evolution 仍然屬於 RGGD。

$$
\boxed{
\text{RGGD}
\not\equiv
\text{LLM Runtime}
}
$$

LLM 是可選的生成、解讀、搜尋與驗證層。

## 5. 生成的真正單位

RGGD 不只生成「內容」。它至少可以生成：Object、Relation、State、Rule、History、Goal、Operator、Grammar。

這使世界不只表面變化，而能改變內部可能性空間。

## 6. 從列表轉為語法

傳統可能列舉：

```text
Sword_001
Sword_002
Sword_003
...
Sword_500
```

RGGD 改為：

```text
Weapon Form
× Material
× Construction
× Edge Geometry
× Enchantment
× Damage
× History
```

但真正實作不能直接做完整笛卡兒積，而應：

$$
\boxed{
\text{Typed Composition}
+
\text{Compatibility Constraints}
}
$$

只生成合法區域。

## 7. 世界內容的三種密度

### 7.1 Catalog Density
定義了多少項。

### 7.2 Combinatorial Density
有多少合法組合。

### 7.3 Causal Generative Density
生成物能否真正影響行為、經濟、歷史、任務、關係與後續生成。

RGGD 最重視第三種。

## 8. 「很多」不等於「生成」

一個遊戲有 5000 件手寫裝備，不代表它具有高 Generative Depth。反之，一個只有 20 種材料、10 種形體、8 種製程的系統，如果它們具有清楚因果語義，可能產生更大的可玩空間。

## 9. 生成內容必須進入世界狀態

如果生成一個物件後，它只存在於 UI 顯示：

$$
X_{\mathrm{generated}}
\rightarrow
\text{Cosmetic Only}
$$

其生成深度有限。

RGGD 更希望：

$$
\boxed{
X_{\mathrm{generated}}
\rightarrow
\text{World State}
\rightarrow
\text{Future Consequence}
}
$$

## 10. 生成的回流

最關鍵區別：

$$
X_{n+1}=\mathcal G_n(X_n)
$$

不是終點。下一步可以：

$$
\mathcal G_{n+1}
=
\operatorname{UpdateGrammar}(\mathcal G_n,X_{n+1}).
$$

這使遊戲從「生成內容」進入「生成條件也會演化」。

## 11. 設計師角色改變

傳統設計師主要製作 Outcome。RGGD 設計師更多是在製作：

$$
\boxed{
\text{Conditions of Valid Outcomes}
}
$$

工作重點轉為定義 primitive、型別、constraint、causal semantics、history feedback 與 validation。

## 12. Failure Modes

最常見錯誤：

1. 把 random 當 generation；
2. 把大量 permutation 當深度；
3. 生成沒有 gameplay consequence；
4. Grammar 沒有 constraint；
5. 生成內容無法保存；
6. 歷史不回流；
7. 所有結果只是 cosmetic reskin。

## 13. 第一級判準

一個系統若要稱為較強的 RGGD，至少應有：

$$
\boxed{
\text{Composition}
+
\text{Constraint}
+
\text{Persistence}
+
\text{Re-entry}
}
$$

其中 Re-entry 指生成結果能參與後續生成。

## 14. 一句話總結

> **RGGD 將遊戲內容從「作者列舉的成品集合」重新定義為「由有限 Primitive、Grammar、Constraint、History 與 Runtime 共同產生的合法世界空間」，並要求生成結果能重新回到系統中，成為下一輪狀態、規則與生成條件。**
