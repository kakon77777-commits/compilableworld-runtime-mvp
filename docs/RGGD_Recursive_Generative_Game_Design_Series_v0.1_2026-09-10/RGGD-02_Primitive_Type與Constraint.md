---
title: "RGGD-02｜Primitive、Type 與 Constraint：有限構件如何形成巨大合法空間"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部方法論論文"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD-02｜Primitive、Type 與 Constraint

## 0. 問題

「有限零件可以產生很多組合」本身並不難。真正困難的是：**如何讓很多組合仍然具有合法性、語義與遊戲價值？**

Naive 模型：

$$
\Omega_{\mathrm{all}}
=
P_1\times P_2\times\cdots\times P_n.
$$

真正可用區域通常只是：

$$
\boxed{
\Omega_{\mathrm{valid}}
\subset
\Omega_{\mathrm{all}}
}
$$

RGGD 的任務不是最大化 $\Omega_{\mathrm{all}}$，而是設計高品質的 $\Omega_{\mathrm{valid}}$。

## 1. Primitive

Primitive 是不能或暫時不需要再向下拆的基本生成構件。生物可用 body plan、tissue、organ、locomotion、sensory component；物品可用 form、material、edge、joint、decoration。

Primitive 不一定是最小物理單位，而是**對當前遊戲語法足夠原子的單位**。

## 2. Type

Type 回答：「這個 Primitive 是什麼類型？它可以被什麼 Grammar 使用？」

```yaml
id: material.iron
type: material.metal
tags:
  - conductive
  - forgeable
  - rigid
```

Type 使系統知道金屬可以進鍛造、布料不能被當成骨頭、肺不能直接裝到沒有氣體交換結構的物件上。

## 3. Constraint 不是敵人

傳統直覺容易認為 Constraint 越多，自由越少。但生成系統中：

$$
\boxed{
\text{Constraint}
=
\text{Condition of Stable Generation}
}
$$

沒有 Constraint，系統得到的不是自由，而是大量 nonsense。

## 4. Constraint 類型

至少可分：Syntax、Semantic、Type、State、Physical、Cultural、Historical、Rights / Authority Constraint。

例如 Historical Constraint：某文明只有在真正接觸某種技術後，才允許生成相關武器。

## 5. Constraint Graph

Constraint 不應全塞在一個巨大 if-else。可以表示成：

$$
G_C=(V_C,E_C).
$$

例如：

```text
wing
├── requires locomotion=flight
├── requires lift_surface
├── conflicts body_mass>threshold
└── modifies energy_cost
```

## 6. Constraint Propagation

若某個選擇 $x_i$ 發生，合法域縮小：

$$
\Omega_{i+1}
=
\Omega_i\cap C(x_i).
$$

生成器應一步一步裁剪可能性，而不是最後才檢查整個成品。

## 7. Typed Composition

合法組合寫成：

$$
x\otimes_T y
$$

表示只有當：

$$
TypeCompatible(x,y)=1
$$

才允許 composition。這比 $x\times y$ 更適合遊戲生成。

## 8. 軟 Constraint

不是所有規則都硬禁止。可以有 hard constraint、soft preference、rarity weight、cultural bias、style penalty。

因此合法空間內仍可有出現概率：

$$
P(x)\propto\exp(Score(x)).
$$

## 9. World-Specific Constraint

同一 Primitive 在不同世界可能有不同合法性。於是：

$$
\Omega_{\mathrm{valid}}
=
\Omega_{\mathrm{valid}}(W_t).
$$

## 10. History-Specific Constraint

文明原本不會造某種武器，但戰爭後逆向工程：

$$
H_t
\rightarrow
Unlock(Rule_{new})
$$

未來合法空間因此改變：

$$
\Omega_{\mathrm{valid}}^{t+1}
\neq
\Omega_{\mathrm{valid}}^t.
$$

## 11. Semantic Leverage per Primitive

Primitive 數量不是唯一目標。10 個 Primitive 若語義弱，只會產生大量換皮；若跨系統作用強，則可能產生大量 gameplay difference。

所以應追求：

$$
\boxed{
\text{Semantic Leverage per Primitive}
}
$$

## 12. Constraint as Design Language

每個 content definition 不只寫「它是什麼」，也寫：

```yaml
requires:
forbids:
modifies:
unlocks:
historical_effect:
```

## 13. Validation

合法性驗證至少分：

$$
\boxed{
\text{Syntactic}
\rightarrow
\text{Semantic}
\rightarrow
\text{State}
\rightarrow
\text{Systemic}
}
$$

不能只做到 schema pass。

## 14. 一句話總結

> **RGGD 的力量不來自把 Primitive 全部亂乘，而是建立 Type 與 Constraint，使有限構件能在不同世界、歷史與狀態下形成巨大但仍可理解、可驗證、可遊玩的合法生成空間。**
