---
title: "RGGD-03｜階層式組合與生成閉包：為什麼不是無限寫 A×B×C×⋯"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部方法論論文"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD-03｜階層式組合與生成閉包

## 0. 問題

如果遊戲生成只寫成：

$$
A\times B\times C\times D\times E\times\cdots
$$

很快會遇到兩個問題：結構不可讀、組合空間爆炸。

真正合理的方法不是把所有 Primitive 一次乘完，而是：

$$
\boxed{
\text{Hierarchical Composition}
}
$$

## 1. 層級封裝

先生成低階 subsystem：

$$
X_1=\mathcal G_1(P_1,\ldots,P_k).
$$

再把 $X_1$ 視為新的高階 object：

$$
X_2=\mathcal G_2(X_1,Y_1,\ldots).
$$

所以：

$$
\boxed{
\text{Composition Result}
\rightarrow
\text{Reusable Higher-Level Unit}
}
$$

## 2. 生物例子

Level 0：bone、muscle、skin、eye、lung、gill、wing。

Level 1：respiratory system、locomotion system、sensory system、skeletal system。

Level 2：

$$
CreatureBody
=
\mathcal G(Systems,Constraints).
$$

Level 3 再加入 diet、habitat、behavior、reproduction、predators。

Level 4 再加入 migration、domestication、extinction、mutation、cultural contact。

## 3. 物品例子

$$
WeaponBody
=
\mathcal G_1(Form,Material,Construction)
$$

再：

$$
Weapon
=
\mathcal G_2(WeaponBody,Decoration,Enchantment,Damage)
$$

再：

$$
HistoricalItem
=
\mathcal G_3(Weapon,OwnerHistory,BattleHistory).
$$

## 4. 生成閉包

定義某個 Grammar $\Gamma$ 下的 closure：

$$
Cl_{\Gamma}(P)
$$

表示從 Primitive 集合 $P$ 出發，在允許 composition 下可形成的所有結構。

RGGD 不要求把 closure 全部 materialize，只需要能描述、抽樣、驗證、按需生成。

## 5. Lazy Generation

巨大 closure 不應全部生成，而應：

$$
\boxed{
\text{Generate on Demand}
}
$$

只在 world creation、encounter、crafting、mutation、historical event 等需要時產生。

## 6. Huge Possibility Space 不等於 Huge Stored State

世界只保存已 materialize 的 objects、seeds、recipes、provenance、必要 grammar state。

所以：

$$
\boxed{
\text{Huge Possibility Space}
\neq
\text{Huge Stored State}
}
$$

## 7. Recipe as Compression

生成物可以保存結構化 Recipe，而不是完整展開所有來源。

```yaml
recipe:
  body_plan: quadruped
  tissue: stone
  respiration: none
  mobility: six_leg
  effect: geothermal
```

## 8. Closure Safety

若 Grammar 可遞迴，必須保證 stop condition、max depth、resource bound、cycle detection、type invariants。

否則：

$$
\text{Generation}
\rightarrow
\text{Infinite Recursion}
$$

## 9. Composition Depth

可定義 $Depth(x)$ 表示生成物經過多少層封裝，但 Depth 越高不一定越好。更重要的是：

$$
\boxed{
\text{Meaningful Dependency Depth}
}
$$

## 10. Cross-Domain Composition

更高階遊戲世界會讓不同 domain 的生成物互相接：

$$
\text{Material}
\rightarrow
\text{Weapon}
\rightarrow
\text{Army}
\rightarrow
\text{War}
\rightarrow
\text{Legend}
\rightarrow
\text{Culture}
$$

這時 closure 不再只是 item generator，而是 world generator。

## 11. Local Closure 與 Global Closure

要區分：

$$
Cl_{\Gamma_i}
$$

與：

$$
Cl_{\Gamma_{\mathrm{world}}}.
$$

某個 crafting system 局部封閉，不代表它和 economy、politics、culture 組合後仍封閉。

## 12. Intermediate State

每一層 composition 後的中間結果都必須是合法 object，不能只保證最後成品合法。

因此：

$$
\boxed{
P(S)
\Rightarrow
P(\Gamma(S))
}
$$

應在每個 admissible intermediate state 保持。

## 13. 生成器也可能被封裝

例如：

$$
G_{\mathrm{weapon}}
+
G_{\mathrm{culture}}
\rightarrow
G_{\mathrm{cultural\ weapon}}
$$

這是後續 Dynamic Grammar 的入口。

## 14. 一句話總結

> **RGGD 不以無限笛卡兒積描述複雜世界，而以階層式 Composition 將低階結果封裝成新的高階 Object，再在不同 Grammar 間遞迴使用；真正需要保存的是生成規則、Recipe 與已 materialize 狀態，而不是整個可能空間。**
