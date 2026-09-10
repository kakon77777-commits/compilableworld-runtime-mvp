---
title: "RGGD-07｜主體與文明作為生成器：角色如何反過來創造規則、文化與技術"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部方法論論文"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD-07｜主體與文明作為生成器

## 0. 核心問題

傳統遊戲中，開發者創造規則，NPC 只能在規則裡活動。

RGGD 更高階的可能是：

$$
\boxed{
\text{Rule}
\rightarrow
\text{Subjects}
\rightarrow
\text{NewRules}
}
$$

角色與文明自己成為世界中的生成器。

## 1. Subject as Generator

主體可表示：

$$
S_i
=
(
Memory,
Belief,
Goal,
Skill,
Resources,
Culture
).
$$

主體可以產生 Item、Plan、Institution、Technology、Tradition、Law、Art、Organization。

## 2. 個人發明

角色可能因問題、技能、可用材料、戰爭需求提出新方案。

流程：

$$
Need
\rightarrow
Experiment
\rightarrow
Candidate
\rightarrow
Validation
\rightarrow
Adoption.
$$

## 3. Civilization Generator

文明可視為更高階 Agent：

$$
C_j
=
(
Population,
Institutions,
Knowledge,
Resources,
Values,
History
).
$$

它能產生 Doctrine、Technology、Law、Architecture、Economy Pattern。

## 4. New Rule 不一定是 Physics Rule

文明最常生成的是 Social Rule、Production Rule、Training Rule、Legal Rule、Cultural Rule。

不應讓 NPC 隨便改宇宙底層物理。

## 5. Innovation Grammar

發明可以由：

$$
Innovation
=
G(
KnownComponents,
Need,
Experiment,
Constraint
)
$$

而不是 AI 任意 hallucinate 一個超科技。

## 6. Discovery 不等於 Adoption

新技術存在不等於文明採用。還需要 Cost、Infrastructure、Ideology、Politics、Skill、Diffusion。

所以：

$$
\boxed{
\text{Discovery}
\neq
\text{Adoption}
}
$$

## 7. Diffusion

技術可以透過 Trade、War、Espionage、Migration、Imitation、Salvage 傳播。

因此 Knowledge 的演化不是只靠 tech tree click。

## 8. Culture Formation

文化不是固定 Tag。

$$
Culture_{t+1}
=
F(
Culture_t,
History_t,
Institutions_t,
Environment_t
).
$$

## 9. Culture 反過來限制生成

文化可以定義 Allowed Weapon、Forbidden Material、Preferred Architecture、Clothing Grammar、Ritual、Naming。

所以：

$$
Culture_t
\rightarrow
\Omega_{\mathrm{valid}}^{t+1}.
$$

## 10. New Institution

當角色與文明遇到反覆問題，可以形成制度：

```text
repeated caravan raids
→ escort guild
→ new profession
→ new contract system
```

這是：

$$
\text{History}
\rightarrow
\text{Institution Grammar}.
$$

## 11. Creator-of-Creators

更高階世界中，主體可以建立會生成內容的系統，例如學派、鍛造流派、魔法學院、機器人設計局。

形成：

$$
\boxed{
\text{Generator}
\rightarrow
\text{Generator Creator}
}
$$

## 12. 主體創造也要有權限域

不能因為「主體可以創造」就允許無限制 mutation。

Creation Scope 應受：

- authority；
- knowledge；
- resource；
- law；
- physics；
- runtime safety；
- civilization capability。

約束。

## 13. LLM 的位置

LLM 可以負責 Proposal、Naming、Plan、Narrative、Innovation Search，但 World Commit 應由 deterministic Validator 決定。

$$
\boxed{
\text{Semantic Proposal}
\rightarrow
\text{World Validator}
\rightarrow
\text{Commit}
}
$$

## 14. 主體死亡後的生成遺產

角色死亡不代表其生成效果消失。

可以留下：School、Weapon Style、Children、Followers、Law、Artifact、Legend。

因此：

$$
\boxed{
\text{Subject}
\rightarrow
\text{Generative Legacy}
}
$$

## 15. Civilization as History Compiler

文明可以把大量個人事件壓縮成穩定制度：

$$
\{e_1,e_2,\ldots,e_n\}
\rightarrow
Institution
$$

再由制度控制後續生成。

這是一種 World-Level Compilation。

## 16. 一句話總結

> **在高階 RGGD 世界中，角色與文明不只是被生成的內容，而是新的生成器：他們會發明、組織、傳播、制度化並留下生成遺產，使世界從「開發者寫好規則」進一步演化為「世界中的主體也能在受控範圍內創造新規則與新可能」。**
