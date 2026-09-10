---
title: "RGGD-08｜組合爆炸、品質控制與驗證：不是生成越多越好"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部方法論論文"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD-08｜組合爆炸、品質控制與驗證

## 0. 核心問題

生成系統最容易犯的錯是：

> 可以生成很多，所以一定比較好。

錯。

$$
|\Omega_{\mathrm{all}}|
$$

可以極大，但：

$$
|\Omega_{\mathrm{meaningful}}|
$$

可能非常小。

## 1. 三個不同問題

$$
\boxed{
\text{Generated}
\neq
\text{Valid}
\neq
\text{Interesting}
}
$$

Generated：產生出來。

Valid：符合世界規則。

Interesting：值得玩家遇到。

## 2. 組合爆炸

若有 $n$ 個維度，每個 $k$ 種：

$$
|\Omega_{\mathrm{all}}|=k^n.
$$

真正系統不能逐個人工 Review。

需要 Early Pruning、Constraint Propagation、Sampling、Simulation、Scoring。

## 3. Validation Pipeline

建議：

$$
\boxed{
\text{Schema}
\rightarrow
\text{Type}
\rightarrow
\text{Constraint}
\rightarrow
\text{Simulation}
\rightarrow
\text{Quality}
}
$$

## 4. Schema Validation

檢查必要欄位、reference、version、syntax。

這是最低層，不代表 gameplay 正確。

## 5. Semantic Validation

檢查 Type、Precondition、World Meaning、Incompatible Parts。

例如有「飛行」Tag 不代表真的能飛；還要看 Body、Mass、Energy、Environment 是否成立。

## 6. Simulation Validation

將 Candidate 放入短模擬：

- 會不會 soft-lock？
- 會不會無限資源？
- 會不會必勝？
- 會不會無法使用？
- 會不會破壞經濟？
- 會不會造成 recursion explosion？

## 7. Novelty

Novelty 不等於 Quality。

可以計算：

$$
D(x,\mathcal C)
$$

看它與既有內容差多少，但：

$$
\boxed{
\text{High Novelty}
\not\Rightarrow
\text{Good}
}
$$

## 8. Redundancy

生成系統常會產生名稱不同、實際玩法相同的內容。

所以應比較：

- mechanic signature；
- visual signature；
- role signature；
- behavior signature；
- causal signature。

## 9. Dominance Check

若新 Item 全面更強、成本更低、沒有缺點，可能破壞系統。

應至少識別明顯 trivial upgrade。

$$
\boxed{
\text{New Content}
\neq
\text{Free Pareto Dominance}
}
$$

## 10. Constraint Learning

若大量 Candidate 因同樣原因失敗，可從 Failure 中產生：

$$
C_{\mathrm{new}}.
$$

因此 Validator 本身也參與 Grammar Refinement。

## 11. Human Review 不會消失

高價值內容可分級：

- Common：程序生成；
- Important：AI + automated review；
- Legendary：human / art-director review。

## 12. AI Reviewer

AI 適合做 Aesthetic Score、Semantic Coherence、Duplicate Detection、Naming、Style Conflict、Narrative Relevance。

但 AI Reviewer 不是唯一 Authority。

## 13. Differential Testing

若新 Grammar 替代舊系統，可比較：

$$
Behavior_{\mathrm{old}}
\leftrightarrow
Behavior_{\mathrm{new}}.
$$

特別適合重建、改造、演算法替換。

## 14. Reproducibility

每次生成應保存：

- seed；
- grammar version；
- input state；
- recipe；
- validation result；
- world version。

使問題可重播。

## 15. Interestingness 是多維的

可以粗分：

$$
Q(x)
=
(
Novelty,
Utility,
Coherence,
StoryPotential,
VisualIdentity
).
$$

不存在單一 Magic Score。

## 16. Cheap Filter → Expensive Review

Validator 本身也有成本。

應採：

$$
\boxed{
\text{Cheap Filter}
\rightarrow
\text{Expensive Review}
}
$$

先用 deterministic rules 排除大部分垃圾，再把少數 Candidate 送給 AI／長模擬／人工。

## 17. Failure as Research

失敗 Candidate 不一定丟掉。

可以記錄：Why Invalid、Which Constraint Missing、Which Grammar Branch Weak。

形成：

$$
\boxed{
\text{Generation Failure}
\rightarrow
\text{Grammar Improvement}
}
$$

## 18. Quality Budget

大型世界應給每類內容不同 Review Budget。

例如普通石頭不需要 LLM Reviewer；新文明法律或核心 Boss 則需要更高驗證層級。

$$
ReviewCost(x)
\propto
Risk(x)+Impact(x).
$$

## 19. 一句話總結

> **RGGD 的工程核心不是讓可能空間無限膨脹，而是建立能早期裁剪、模擬、比較、驗證與學習失敗的生成管線，使系統把算力集中在「合法而有意義的可能性」上。**
