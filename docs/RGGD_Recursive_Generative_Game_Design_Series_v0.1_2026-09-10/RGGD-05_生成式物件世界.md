---
title: "RGGD-05｜生成式物件世界：生物、物品、材料、製造與技能的共同語法"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部方法論論文"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD-05｜生成式物件世界

## 0. 目標

本篇把 RGGD 從抽象 Grammar 壓到遊戲內容。

核心主張：生物、物品、材料、製造與技能不必各自是一份巨大 Catalog；它們可以共享一套跨 domain 的生成邏輯。

## 1. Material

材料不是名稱，而是一組 property：

$$
M=
(
density,
hardness,
elasticity,
conductivity,
melting,
corrosion,
magic,
biology
).
$$

因此新增材料時，它可以自動影響 weapon、armor、building、crafting、trade、ecology。

## 2. Item

物品可表示：

$$
I=
(
Form,
Material,
Construction,
Function,
Decoration,
Condition,
History
).
$$

同一 Sword Form 可以套不同 Material；同一 Material 也可以進不同 Item。

## 3. Process

製造 Recipe 不應全是手寫成品。

更一般：

$$
Output
=
Process(
Inputs,
Tool,
Skill,
Environment
).
$$

例如：

```text
forge
+ metal
+ blade form
+ skilled smith
→ weapon
```

## 4. Property Propagation

成品 property 應由來源傳播：

$$
P_{\mathrm{item}}
=
F(
P_{\mathrm{form}},
P_{\mathrm{material}},
P_{\mathrm{process}},
P_{\mathrm{history}}
).
$$

這樣新增 Material 不需重新手寫所有 Item Variant。

## 5. Creature

生物可以表示：

$$
C=
(
BodyPlan,
Tissue,
Organs,
Locomotion,
Senses,
Metabolism,
Behavior,
Ecology
).
$$

每一部分都必須反映 gameplay，而不是只改名稱與圖。

## 6. Functional Coherence

例如：

- flight 需要 lift structure；
- underwater respiration 需要對應 organ；
- high mass 影響 locomotion；
- stone tissue 改變 metabolism；
- sensory loss 影響 behavior。

生成器不能只追求怪異，而要保持：

$$
\boxed{
\text{Functional Coherence}
}
$$

## 7. Skill

技能也可以組合：

$$
S=
(
Action,
Target,
Resource,
Condition,
Effect,
Cost,
Timing
).
$$

例如：

```text
dash
+ line target
+ stamina
+ armor break
+ cooldown
```

## 8. Ability Grammar

不同文明可以共享 Primitive，但擁有不同 Grammar。

文明 A 可偏 ritual magic、spirit binding；文明 B 偏 engineering、robotics。兩者都可能使用 energy、range、duration、target 等抽象 Primitive，但合法 composition 不同。

## 9. Cross-Domain Coupling

最重要的是：

$$
\boxed{
\text{Material}
\rightarrow
\text{Item}
\rightarrow
\text{Combat}
\rightarrow
\text{Economy}
\rightarrow
\text{History}
}
$$

如果生成只停在「多一把劍」，價值有限。

## 10. Artifact Emergence

普通物品可以因歷史變成神器：

$$
I_0
+
\text{Owner}
+
\text{Battle}
+
\text{Event}
\rightarrow
I^\star.
$$

這比手寫 `LegendarySword_001` 更能產生世界感。

## 11. Species History

普通種族也能因 migration、isolation、domestication、radiation、magic、war 產生新的 phenotype 或 behavior。

## 12. Culture–Object Feedback

文化可以影響 weapon form、armor style、architecture、food、ritual；物件又能反過來改變文化。

$$
\boxed{
Culture
\leftrightarrow
Object
}
$$

例如新武器改變軍事 doctrine，新食物改變聚落結構，新材料改變建築語法。

## 13. Economy Re-entry

新物件若可被交易：

$$
GeneratedItem
\rightarrow
Market
\rightarrow
Demand
\rightarrow
Production
$$

就會形成真正經濟回流，而不是 loot list 裝飾。

## 14. Visual Runtime Interface

生成式物件應能投影到視覺 Recipe：

$$
ObjectState
\rightarrow
VisualRecipe.
$$

例如：material → texture、damage → overlay、culture → palette、rank → decoration。

這可直接接 Composable Visual Runtime。

## 15. 內容覆蓋策略

不是所有生成物都要 bespoke art。

可採：

$$
\boxed{
\text{Procedural Base}
+
\text{Semi-Custom Important}
+
\text{Bespoke Legendary}
}
$$

## 16. 一句話總結

> **生成式物件世界的重點，不是把 Item、Creature、Skill 各自生成很多，而是讓材料、形體、製程、能力、文化與歷史共享可傳播的語義 Property，使少量 Primitive 可以跨多個 Gameplay Domain 產生真正不同的世界結果。**
