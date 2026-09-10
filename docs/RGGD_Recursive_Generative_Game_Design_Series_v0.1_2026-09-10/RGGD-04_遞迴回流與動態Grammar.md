---
title: "RGGD-04｜遞迴回流與動態 Grammar：生成結果如何成為新的生成條件"
author: "Neo.K / EveMissLab"
date: "2026-09-10"
version: "v0.1"
document_type: "內部方法論論文"
canonical_status: "ACTIVE"
language: "zh-TW"
---

# RGGD-04｜遞迴回流與動態 Grammar

## 0. 核心問題

一般生成器可以寫成：

$$
X=\mathcal G(P).
$$

生成後結束。

RGGD 更強的形式是：

$$
X_{n+1}
=
\mathcal G_n(X_n,C_n,H_n,E_n)
$$

並允許：

$$
\boxed{
X_{n+1}
\rightarrow
\mathcal G_{n+1}
}
$$

也就是生成結果會改變未來生成規則。

## 1. Re-entry

若生成結果 $X_{n+1}$ 可以重新進入下一輪生成並影響可能空間，稱為 Re-entry。

例如：

- 新材料成為 crafting primitive；
- 新技術成為新 recipe；
- 新文化形成新 style grammar；
- 新職業形成新 training path；
- 新物種成為新的 ecological actor。

## 2. 四種回流

### 2.1 Object Re-entry
新物件重新成為輸入。

### 2.2 Relation Re-entry
新關係改變後續生成。

### 2.3 Rule Re-entry
新規則加入規則庫。

### 2.4 Grammar Re-entry
整個 composition grammar 改變。

這四者的生成強度不同，必須分開記錄。

## 3. Dynamic Generator Family

定義：

$$
\boxed{
\mathcal G_n
\rightarrow
\mathcal G_{n+1}
}
$$

這表示未來合法生成方式本身可演化，而不是只有內容集合擴大。

## 4. Grammar-Generative Event

若事件 $e$ 產生新的合法 composition rule：

$$
e\rightarrow\Gamma_{\mathrm{new}}
$$

則它不是普通 content generation，而是：

$$
\boxed{
\text{Grammar-Generative Event}
}
$$

## 5. 例子：科技發明

文明原本只有：

```text
metal forging
wood construction
```

戰爭後取得：

```text
energy crystal
```

經研究後形成：

```text
hybrid energy-metal forging
```

這不只是多一把武器，而是：

$$
\boxed{
\Gamma_{craft}^{t+1}
\neq
\Gamma_{craft}^{t}
}
$$

未來所有武器生成空間都改變。

## 6. 例子：新職業

角色長期使用 shield、drone 與 field repair。世界原本沒有這個職業。

若系統從行為中抽取出：

```text
Field Drone Warden
```

並正式形成 training rules、equipment profile、recruitment conditions，則：

$$
\text{Actor History}
\rightarrow
\text{New Class Grammar}
$$

## 7. Ontology Change

最強形式不是新增 value，而是新增 Type。

例如世界原本只有：

- human；
- machine。

某歷史事件形成：

- human-machine merged subject。

此時：

$$
TypeSet_{t+1}
\neq
TypeSet_t.
$$

這是 Ontology Change。

## 8. Recursive Frontier Renewal

每次生成後，都可能建立新的 frontier：

$$
F_n
\rightarrow
Y_{n+1}
\rightarrow
F_{n+1}.
$$

所以探索空間不是固定的。世界會自己產生新的「下一步可能性」。

## 9. 不是所有新東西都應提升 Grammar

若任何新物件都自動生成新 rule：

$$
\text{Noise}
\rightarrow
\text{Grammar Explosion}
$$

因此必須有 promotion threshold，例如：

- 重複出現；
- 足夠穩定；
- 有 gameplay value；
- 可被其他 object reuse；
- 通過 simulation。

## 10. Bounded Grammar Mutation

自我擴張不等於無限制自我修改。

必須有：

$$
\boxed{
\text{Bounded Grammar Mutation}
}
$$

新 Grammar 必須經：

- type check；
- invariant check；
- compatibility；
- resource limits；
- authority；
- simulation。

## 11. Grammar Promotion

新規則不直接進 canonical grammar。

建議：

```text
candidate rule
→ sandbox
→ simulation
→ validation
→ promotion
```

即：

$$
\boxed{
\text{Proposal}
\rightarrow
\text{Validation}
\rightarrow
\text{Grammar Commit}
}
$$

## 12. Rule Provenance

動態世界中的 rule 也要有 history：

```yaml
rule_id:
created_by:
created_at:
trigger_event:
parent_rules:
validation:
```

玩家與 AI 都能追查：「這個文明為什麼現在會這樣造東西？」

## 13. Stable Core 與 Evolvable Edge

不是所有規則都允許變。

$$
\boxed{
\Gamma
=
\Gamma_{\mathrm{core}}
+
\Gamma_{\mathrm{evolvable}}
}
$$

Core 可以包括 save integrity、安全、不變量與基本物理邊界；Evolvable 可以包括 technology、style、crafting、culture、tactics、institutions。

## 14. Meta-Generation

若 Generator 可以產生 Generator：

$$
G\rightarrow G'
$$

則進入 Meta-Generation。

但遊戲設計上需要限制：可修改 domain、最大層數、promotion frequency 與 rollback。

## 15. 玩家可見性

Dynamic Grammar 不應全是黑箱。玩家最好能看到新技術、新流派、新制度、新物種、新 Recipe 的歷史來源。

這使 emergent generation 本身成為 gameplay。

## 16. 一句話總結

> **RGGD 的關鍵不是只讓 Grammar 產生內容，而是讓生成結果在驗證後重新成為新的 Primitive、Relation、Rule、Type 或 Grammar，使世界的合法生成空間能隨歷史逐步改變；這就是從程序生成走向動態生成世界的核心。**
