# CompilableWorld Executable World Platform
## 世界狀態機、遊戲引擎／渲染器綁定與 AI-Native 世界組裝技術白皮書

**版本：** v0.1
**日期：** 2026-08-10
**狀態：** Architecture Expansion / Technical Whitepaper
**作者：** Neo.K × AI 協作整理
**專案代碼：** CW-EWP

---

# 0. 文件目的

本文件建立在現有 **CompilableWorld Runtime MVP v0.1.1** 之上。

現有 MVP 已經完成的重要邊界包括：

- JSON / CSV / Manifest Authoring Layer；
- Compiler + Validators；
- Runtime Package；
- World Kernel；
- ActionIR；
- MSSP / TMS Module；
- StateDelta；
- EventIR；
- Atomic Commit；
- Event Log；
- Snapshot / Replay；
- Terminal Gateway；
- Web Gateway；
- Studio Read-only Projection；
- Scoped StateIR；
- Action-scope Behavior；
- FunctionIR；
- ScenarioIR；
- MCP / Agent 接入相關安全與協調基礎。

現有 Runtime 的核心邏輯已經是：

```text
JSON / CSV / Manifest
        ↓
Compiler + Validators
        ↓
Runtime Package
        ↓
World Kernel
        ↓
ActionIR
        ↓
MSSP / TMS Module
        ↓
StateDelta + EventIR
        ↓
Atomic Commit / Event Log
        ↓
Projection
        ↓
Terminal / Web / Studio / Agent
```

本白皮書的目的不是推翻此架構。

而是正式回答下一個問題：

> **如果 CompilableWorld 的世界狀態機、世界模組、Action／Event／Projection 契約持續擴充，它如何從「可編譯世界 Runtime」進一步成為可與遊戲引擎、直接渲染器、AI Agent 與多種前端連接的通用 Executable World Platform？**

---

# 1. 核心命題

傳統遊戲架構通常接近：

$$
\boxed{
GameEngine
\supset
WorldLogic
}
$$

世界規則、角色狀態、任務、戰鬥、經濟、渲染與輸入常被放在同一個 Engine Project 之內。

CompilableWorld 的長期方向則改為：

$$
\boxed{
WorldRuntime
\supset
ExecutableWorldLogic
}
$$

而：

- Game Engine；
- Renderer；
- Physics；
- Audio；
- Input；
- UI；
- Web；
- Terminal；
- AI Agent；

都可以被視為世界 Runtime 的不同 Client、Adapter 或 Projection。

因此最終核心可以寫成：

$$
\boxed{
World
\neq
GameEngine
}
$$

以及：

$$
\boxed{
WorldRuntime
+
PresentationAdapter
=
PlayableWorld
}
$$

---

# 2. 從「世界狀態機」到「可執行世界」

一組狀態機本身還不是完整世界。

CompilableWorld 要成為 Executable World Platform，至少需要五類結構：

## 2.1 World State

世界中目前「是什麼」。

例如：

- NPC；
- 國家；
- 領地；
- 經濟；
- 關係；
- 任務；
- 世界時間；
- 物品；
- 城鎮；
- 戰爭；
- 天氣；
- 歷史。

---

## 2.2 State Transition

世界如何改變。

現有 MVP 已經透過：

- Scoped StateIR；
- Quest transitions；
- Action-scope behaviors；
- Runtime Modules；

建立 bounded、可驗證、可 replay 的狀態轉移路徑。

---

## 2.3 Action Vocabulary

世界中的 Actor 可以做什麼。

現有 ActionIR 是唯一正規化 Action Boundary。

未來 Action Vocabulary 可擴張為：

```text
move
talk
attack
defend
trade
buy
sell
hire
fire
craft
build
sleep
eat
steal
arrest
heal
marry
migrate
work
declare_war
sign_treaty
invest
research
govern
```

所有入口：

- 玩家；
- AI；
- MCP；
- Game Engine；
- Web；
- Script；

都應轉成：

$$
\boxed{
ActionIR
}
$$

而不是直接修改世界狀態。

---

## 2.4 Causal Event

已經發生的世界事實。

現有 EventIR 應繼續維持：

> **Committed causal fact and cross-module communication primitive**

例如：

```text
character.moved
dialogue.responded
combat.damage
character.defeated
item.transferred
quest.completed
faction.war_declared
market.price_changed
npc.migrated
```

---

## 2.5 Projection

不同 Client 如何看見同一世界。

因此：

$$
W_t
\rightarrow
P_i(W_t)
$$

其中 $P_i$ 可以是：

- Terminal Projection；
- Web Projection；
- RPG Projection；
- Strategy Projection；
- Map Projection；
- AI Observation；
- Studio Projection；
- Renderer Projection。

---

# 3. 核心架構升級

長期架構：

```text
                    AUTHORING
                       │
          JSON / CSV / YAML / EveGlyph
                       │
                       ▼
                World Compiler
                       │
                       ▼
                Runtime Package
                       │
                       ▼
┌──────────────────────────────────────────┐
│          CompilableWorld Runtime         │
│                                          │
│  Entity Registry                         │
│  StateStore                              │
│  Scoped StateIR                          │
│  Action Behaviors                        │
│  Action Runtime                          │
│  Scheduler                               │
│  MSSP / TMS Modules                      │
│  FunctionIR                              │
│  Event Bus                               │
│  Event Log                               │
│  Snapshot / Replay                       │
│  Scenario Runtime                        │
│  Projection Runtime                      │
│  Agent / MCP Gateway                     │
└──────────────────┬───────────────────────┘
                   │
          World Binding Protocol
                   │
      ┌────────────┼─────────────┐
      ▼            ▼             ▼
   Terminal       Web       Game / Render
                                │
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
                Bakin         Godot      Direct Renderer
                                              │
                                   SDL / bgfx / WebGPU /
                                   Vulkan / DirectX ...
```

---

# 4. World Runtime 是 Authority

現有 Contract Inventory 已經明確建立：

| Domain | Authority |
|---|---|
| Canon / authored rules | Authoring files + Compiler |
| Initial executable world | Runtime Package |
| Current world state | StateStore through Kernel commit |
| Causal history | committed EventIR sequence |
| Natural-language narrative | Projection only |

這個原則必須延伸到 Game Engine Binding。

也就是：

> **Game Engine 不因為能畫出某件事，就自動成為該世界事實的 Authority。**

---

# 5. Authority Matrix

不同資料應由最適合的系統擁有。

第一版建議：

| Domain | Authoritative Layer |
|---|---|
| Canon entities | Runtime Package |
| NPC existence | World Runtime |
| NPC occupation | World Runtime |
| NPC faction | World Runtime |
| Relationship | World Runtime |
| Economy | World Runtime |
| Quest state | World Runtime |
| World history | Event Log |
| Semantic location | World Runtime |
| Exact XYZ position | Engine / Simulation Subsystem |
| Animation frame | Engine |
| Shader | Renderer |
| Camera | Engine |
| Audio playback position | Engine |
| NavMesh | Engine |
| Physics contact | Engine |
| Combat semantic result | Configurable |
| World time | World Runtime |
| Render interpolation | Engine |
| AI memory evidence | AMK / governed memory layer |
| AI proposal | Non-authoritative until validated |

---

# 6. 三類狀態

## 6.1 Canonical World State

世界 Runtime 唯一權威。

例如：

```text
npc.00421.alive = true
npc.00421.job = blacksmith
npc.00421.faction = kingdom.north
npc.00421.semantic_location = town.ironvale.smithy
npc.00421.wealth = 423
npc.00421.relationship.player = 17
```

---

## 6.2 Engine-local State

不進入 Canonical World State。

例如：

```text
animation_frame
shader_parameter
camera_shake
particle_timer
render_lod
footstep_phase
temporary_collision_contact
```

---

## 6.3 Mirrored / Shared State

兩邊都需要，但必須宣告 Authority。

例如：

- HP；
- Position；
- Combat State；
- Door State；
- Current Scene。

這些必須透過契約標記：

```text
authority = world
authority = engine
authority = subsystem
authority = negotiated
```

避免：

```text
World says A
Engine says B
Save says C
```

---

# 7. Semantic State 與 Physical State

這是 World Runtime 與 Renderer／Game Engine 分離的核心。

例如位置：

## Semantic Position

```text
continent.north
region.iron_valley
town.ironvale
building.smithy
```

## Physical Position

```text
Vector3(127.31, 2.0, -82.17)
```

兩者不是同一種資訊：

$$
P_{semantic}
\neq
P_{physical}
$$

需要一個 Adapter Mapping：

$$
\Phi:
P_{semantic}
\rightarrow
P_{physical}
$$

世界 Runtime 不需要理解 NavMesh 的所有頂點。

Renderer 也不需要決定：

> 這名 NPC 的法律國籍是什麼。

---

# 8. World–Game Binding Protocol

新增正式層：

# **WGBP — World–Game Binding Protocol**

目標：

> 定義任何 Game Engine、Renderer 或 Presentation Runtime 如何與 CompilableWorld 交換世界語義。

第一版至少包含：

1. `EngineCapability`
2. `WorldSession`
3. `EntityBinding`
4. `ProjectionSubscription`
5. `ProjectionSnapshot`
6. `ProjectionDelta`
7. `EngineIntent`
8. `ActionReceipt`
9. `EngineEvent`
10. `ClockContract`
11. `AuthorityMatrix`
12. `SceneHydration`
13. `SceneDehydration`
14. `Reconnect`
15. `SaveBarrier`

---

# 9. EngineCapability

Client 連線時先宣告能力。

例如：

```json
{
  "contract": "compilableworld.engine-capability/v0.1",
  "client_id": "godot-client-01",
  "presentation": "3d",
  "physics": true,
  "audio": true,
  "ui": true,
  "max_active_entities": 500,
  "supports_streaming": true,
  "supports_animation": true,
  "supports_semantic_spawn": true,
  "supports_combat_collision": true
}
```

Runtime 不應假設所有 Client 都能做 3D Physics。

Terminal 的 Capability 可以很小。

Bakin 的 Capability 與 Godot 也可能不同。

---

# 10. EntityBinding

WorldEntity 與 EngineObject 必須分離。

例如：

```text
World Entity:
npc:000000004211
```

Godot Instance：

```text
instance_id: 835172
```

物件卸載後重新生成：

```text
instance_id: 912402
```

世界身份不能因此改變。

所以：

$$
\boxed{
EntityBinding
=
(WorldEntityId,\ EngineInstanceId,\ Generation)
}
$$

建議：

```json
{
  "world_entity_id": "npc:000000004211",
  "engine_instance_id": "godot:835172",
  "generation": 4,
  "binding_type": "character"
}
```

Generation 改變後，舊 binding 立即失效。

---

# 11. WorldEntity 不等於 EngineObject

這一點必須成為核心公理：

$$
\boxed{
WorldEntity
\neq
EngineObject
}
$$

假設世界中：

$$
N_{world}=100000
$$

但玩家附近只有：

$$
N_{active}=72
$$

則：

```text
100,000 World Entities
        │
        │ Active Projection
        ▼
     72 Entities
        │
        ▼
  72 Engine Objects
```

其他 99,928 個 NPC 仍存在。

只是沒有被具象化。

---

# 12. Projection Subscription

Game Client 不需要整個世界。

它只訂閱：

```text
player current region
nearby entities
visible quest
local market
weather
current war state
```

例如：

```json
{
  "scope": "scene:town.ironvale",
  "actor_id": "player.neo",
  "projection": "rpg.scene/v0.1"
}
```

---

# 13. ProjectionSnapshot

進入場景時：

```text
Engine:
scene_enter(town.ironvale)
       ↓
Adapter:
subscribe(scene)
       ↓
Runtime:
ProjectionSnapshot
```

例如：

```json
{
  "scene_id": "town.ironvale",
  "generation": 184,
  "entities": [
    {
      "entity_id": "npc.blacksmith.017",
      "archetype": "human.blacksmith",
      "semantic_state": "working",
      "appearance": "blacksmith.male.03"
    }
  ],
  "world": {
    "weather": "rain",
    "owner": "kingdom.north",
    "war_state": "peace"
  }
}
```

---

# 14. ProjectionDelta

Snapshot 後只傳變化：

```json
{
  "generation": 185,
  "changes": [
    {
      "op": "update",
      "entity_id": "npc.blacksmith.017",
      "field": "semantic_state",
      "value": "closing_shop"
    }
  ]
}
```

避免每 Tick 傳完整世界。

---

# 15. EngineIntent → ActionIR

任何 Game Engine 輸入，都不得直接寫 StateStore。

例如玩家點擊 NPC：

```text
Mouse / Controller
      ↓
Godot
      ↓
EngineIntent
      ↓
Adapter
      ↓
ActionIR
      ↓
Kernel
```

例如：

```json
{
  "verb": "talk",
  "actor": "player.neo",
  "target": "npc.blacksmith.017",
  "args": {
    "topic": "work"
  }
}
```

現有 Runtime 原則仍保持：

```text
ActionIR
→ module.evaluate()
→ StateDelta
→ Kernel validation
→ Atomic Commit
→ EventIR
```

---

# 16. EventIR → EngineEvent

Runtime 提交：

```text
dialogue.responded
relationship.changed
quest.available
```

Game Adapter 再翻成：

```text
play animation
show text
update quest UI
play sound
```

因此：

$$
\boxed{
Input
\rightarrow
Intent
\rightarrow
WorldTransition
\rightarrow
Presentation
}
$$

---

# 17. Game Engine 不得成為第二 Rules Engine

重要禁止事項：

```text
Godot:
relationship += 5
```

或：

```text
Bakin:
quest_completed = true
```

如果這些屬於 World Runtime Authority。

正確方式：

```text
Engine
→ ActionIR / Engine Event
→ Module
→ StateDelta
→ Commit
```

Game Engine 可以有自己的 Physics Rules。

但不能悄悄複製：

- Quest Rules；
- Economy Rules；
- Relationship Rules；
- Faction Rules；

形成第二套世界真相。

---

# 18. Multi-Rate Runtime

Renderer、Combat 與 World Simulation 不需要同頻率。

至少三個 Clock：

## 18.1 Render Clock

$$
f_{render}
\approx
60\sim144Hz
$$

處理：

- animation；
- interpolation；
- camera；
- shader；
- visual effects。

---

## 18.2 Gameplay Clock

$$
f_{gameplay}
\approx
10\sim30Hz
$$

處理：

- combat；
- semantic movement；
- active AI；
- interaction；
- local simulation。

---

## 18.3 World Clock

$$
f_{world}
\approx
0.1\sim1Hz
$$

或使用遊戲時間：

```text
1 tick = 1 minute
1 tick = 10 minutes
1 tick = 1 hour
```

處理：

- economy；
- NPC schedule；
- migration；
- production；
- diplomacy；
- war；
- long-term relationship；
- history。

因此：

$$
\boxed{
f_{render}
\gg
f_{gameplay}
\gg
f_{world}
}
$$

---

# 19. Runtime Host 擁有 Authoritative Time

現有 Action-scope Contract 已經確立：

> Runtime host owns time advancement.

此原則應延續。

Game Client 可以：

- Request；
- Observe；
- Animate；

但不能任意：

> 讓 authoritative world tick 快進 100000。

除非擁有明確 operator / simulation authority。

---

# 20. 即時戰鬥的兩種 Authority Mode

不是所有遊戲都應由 World Kernel 計算每次碰撞。

## Mode A — World Authoritative Combat

適合：

- 回合制；
- 卡牌；
- 戰棋；
- MUD；
- 策略；
- 中低頻 RPG。

```text
attack intent
↓
World Runtime
↓
hit / damage
↓
EventIR
↓
Engine animation
```

---

## Mode B — Subsystem Authoritative Combat

適合：

- Action RPG；
- FPS；
- 高速 physics combat。

```text
Engine Physics
↓
collision confirmed
↓
Combat Semantic Event
↓
World Runtime
↓
persistent consequence
```

例如：

```text
physics hit
```

不是世界歷史。

但：

```text
npc.17 injured by npc.32
```

是世界事實。

---

# 21. Physics Truth 與 Semantic Truth

因此：

$$
\boxed{
PhysicsTruth
\rightarrow
SemanticEvent
\rightarrow
WorldTruth
}
$$

世界 Runtime 不需要每幀知道劍 Collider 的位置。

它只需要知道：

> 這次經過授權的 Combat Subsystem 確認了一次有效命中。

---

# 22. Scene Hydration

場景載入：

```text
scene subscribe
↓
projection snapshot
↓
instantiate engine objects
↓
bind entities
```

稱為：

# **Hydration**

---

# 23. Scene Dehydration

玩家離開場景：

```text
capture required shared state
↓
validate
↓
commit semantic deltas
↓
despawn engine objects
↓
release bindings
```

稱為：

# **Dehydration**

WorldEntity 不消失。

只是不再有 EngineObject。

---

# 24. Save Barrier

Engine 與 World Runtime 必須建立一致性保存點。

建議：

```text
save.barrier.begin
↓
freeze authoritative mutation boundary
↓
flush World State
↓
flush Event Log
↓
flush engine-shared persistent state
↓
generation hash
↓
save.barrier.commit
```

這可直接延續既有 Legacy World Virtualization 與 Runtime Snapshot / Replay 思路。

---

# 25. Sidecar-first

CompilableWorld 長期不應先變成：

> Godot-only Plugin。

建議：

$$
\boxed{
CompilableWorld
=
StandaloneHeadlessWorldRuntime
}
$$

第一優先：

```text
Game.exe
   │
 IPC / Local Transport
   ▼
CompilableWorld.exe
```

優點：

- crash isolation；
- AI 不阻塞 rendering；
- World 可在沒有 Game Client 時運行；
- 可讓多 Client 共用；
- 可做 Server；
- 可替換引擎；
- 更容易測試；
- 世界不被單一引擎生命週期綁死。

---

# 26. Embedded Mode

仍可提供：

```text
Godot
└─ CompilableWorld Library
```

適用：

- 純單機；
- 低 latency；
- 小世界；
- 簡單部署。

因此最終應支援：

```text
runtime_mode:
  embedded
  sidecar
  server
```

---

# 27. 直接 Renderer 路線

當 World Runtime 足夠成熟後：

> Game Engine 不是必要條件。

可以：

```text
CompilableWorld
      │
Presentation Adapter
      │
      ├─ Renderer
      ├─ Physics
      ├─ Audio
      └─ Input
```

Renderer 可使用：

- SDL；
- bgfx；
- WebGPU；
- Vulkan；
- DirectX；
- OpenGL；
- 其他 Graphics Runtime。

這時傳統 Engine 被拆成：

$$
\boxed{
Renderer
+
Physics
+
Audio
+
Input
+
AssetLoader
}
$$

而世界規則全部位於 CompilableWorld。

---

# 28. Presentation Semantics

Renderer 不能只收到：

> draw sprite 37。

World Runtime 應輸出語義：

```json
{
  "entity": "npc.42",
  "archetype": "human.blacksmith",
  "activity": "working",
  "emotion": "happy",
  "equipment": ["tool.hammer"],
  "appearance": "blacksmith.male.03"
}
```

Adapter 再決定：

- 2D sprite；
- pixel；
- low-poly 3D；
- realistic 3D；
- VR avatar。

因此：

$$
\boxed{
SemanticState
\rightarrow
VisualRepresentation
}
$$

---

# 29. Presentation Archetype Registry

建議新增：

```text
presentation/
├─ archetypes
├─ animations
├─ equipment_visuals
├─ environment
├─ audio_cues
└─ ui_semantics
```

例如：

```json
{
  "archetype_id": "human.blacksmith",
  "semantic_tags": [
    "humanoid",
    "worker",
    "blacksmith"
  ]
}
```

而不是綁定某個 Godot Scene Path。

---

# 30. Engine Adapter

長期：

```text
adapters/
├─ terminal/
├─ web/
├─ bakin/
├─ godot/
├─ unity/
├─ unreal/
├─ renderer/
└─ legacy/
```

同一 Runtime Package 不因 Adapter 不同而改寫核心世界規則。

---

# 31. Bakin Adapter

第一個高價值實驗 Adapter 可選 Bakin。

理由不是它最自由。

反而是：

> **它會逼迫 CompilableWorld 證明自己不依賴 Engine-specific internals。**

Bakin Adapter 可先只提供：

- NPC projection；
- shop projection；
- quest projection；
- dialogue；
- world event；
- faction flag；
- basic combat handoff。

---

# 32. Godot Adapter

Godot 可作為第二個更深 Adapter。

可能提供：

```text
CompilableWorldClient
├─ WorldSession
├─ EntityBinding
├─ ProjectionSubscription
├─ ActionSubmitter
├─ EventListener
├─ ClockSync
├─ SceneHydrator
└─ SaveBarrier
```

概念 API：

```gdscript
var world = CompilableWorld.connect("localhost:7331")

world.subscribe("scene:town.ironvale")

world.action({
    "verb": "talk",
    "target": "npc.blacksmith.017"
})

world.on_event(_handle_world_event)
```

---

# 33. Legacy Game Adapter

既有 Legacy World Virtualization 研究可視為：

> **WGBP 的特殊 Adapter。**

原本：

```text
Legacy Game
+
Bridge
+
World Host
+
Sidecar DB
+
Active Set Projection
```

可以重新理解為：

```text
CompilableWorld
+
Legacy Engine Adapter
+
Active Set Projection
```

因此新遊戲、Bakin 與老遊戲可以進入同一個整體架構。

---

# 34. 模組積木化

世界狀態機持續擴張後，建議形成：

```text
modules/
├─ npc/
│  ├─ hunger
│  ├─ fatigue
│  ├─ schedule
│  ├─ occupation
│  ├─ relationship
│  ├─ family
│  └─ migration
│
├─ economy/
│  ├─ production
│  ├─ market
│  ├─ supply
│  ├─ demand
│  └─ trade
│
├─ politics/
│  ├─ faction
│  ├─ diplomacy
│  ├─ territory
│  └─ war
│
├─ rpg/
│  ├─ attributes
│  ├─ inventory
│  ├─ equipment
│  ├─ skill
│  ├─ combat
│  └─ quest
│
└─ world/
   ├─ time
   ├─ weather
   ├─ geography
   ├─ event
   └─ history
```

---

# 35. World Module Manifest

遊戲建立可以越來越接近組合：

```yaml
world:
  time: true
  weather: true
  history: true

npc:
  schedule: true
  occupation: true
  relationship: true
  family: false
  migration: true

economy:
  production: true
  market: true
  trade: true

politics:
  factions: 5
  diplomacy: true
  war: true

rpg:
  combat: action
  equipment: true
  quests: dynamic
```

因此：

$$
\boxed{
Configuration
+
Content
+
Assets
\rightarrow
ExecutableWorld
}
$$

---

# 36. Genre 作為模組集合

遊戲類型不一定是固定 Engine Template。

可以近似：

$$
\boxed{
Genre
=
ModuleSet
+
Projection
+
RuleProfile
}
$$

---

# 37. Dating / Social Simulation

```text
NPC
Schedule
Relationship
Memory
Dialogue
Calendar
```

---

# 38. Meine-Reise-like

```text
NPC
Occupation
Economy
Faction
Territory
War
Migration
Quest
```

---

# 39. CRPG

```text
NPC
Relationship
Quest
Inventory
Combat
Faction
Dialogue
```

---

# 40. 4X

```text
Faction
Population
Economy
Territory
Diplomacy
War
Technology
```

---

# 41. City Simulation

```text
Population
Job
Production
Market
Migration
Building
Infrastructure
```

---

# 42. 同一個世界可以是不同遊戲

假設：

$$
W_t
$$

是一個共同世界。

則：

$$
W_t
\rightarrow
\begin{cases}
P_{RPG}(W_t)\\
P_{Strategy}(W_t)\\
P_{Management}(W_t)\\
P_{Simulation}(W_t)\\
P_{Agent}(W_t)
\end{cases}
$$

一個 Client：

> 我是一名冒險者。

另一個 Client：

> 我控制國家。

AI Client：

> 我是某個 NPC 國王。

它們可以共享同一個 Event Log 與 World State。

---

# 43. Projection 不只是 UI

Projection 決定：

- 可見資訊；
- 可操作粒度；
- 可用 Action；
- 更新頻率；
- 空間表示；
- 角色身份；
- 權限。

因此 RPG 與 Strategy 不是一定要有兩套世界。

可能只是：

> **同一世界的兩個操作投影。**

---

# 44. AI 的角色重新定義

如果世界模組與語義契約足夠完整，AI 不再主要負責：

> 「每次從零寫一套遊戲。」

而是：

# **World Assembler**

---

# 45. AI World Assembly

使用者：

> 做一個低魔幻想世界，三國戰爭、500 NPC、有商人、傭兵與領地戰。

AI：

```text
Natural Language Intent
        ↓
World Specification
        ↓
Module Selection
        ↓
Entity Generation
        ↓
Rule Configuration
        ↓
Scenario Validation
        ↓
Asset Generation / Selection
        ↓
Presentation Binding
        ↓
Playable World
```

---

# 46. AI 不直接成為 World Authority

現有 CompilableWorld 已確立：

> AI / MCP adapter 可以構造 ActionIR，但不得直接寫 StateStore。

此原則必須保持。

因此：

```text
AI
↓
Proposal
↓
Schema / Permission / Module Validation
↓
ActionIR
↓
Kernel
↓
StateDelta
↓
Commit
```

---

# 47. AI 可以操作的五個層級

## Level 1 — Authoring Assistant

生成：

- NPC；
- Quest；
- Faction；
- Item；
- State Machine 草稿。

---

## Level 2 — World Assembler

選擇與配置：

- 模組；
- Rules；
- Templates；
- World topology。

---

## Level 3 — Runtime Actor

AI 是：

- NPC；
- 國王；
- 商人；
- Agent。

只能透過 ActionIR 行動。

---

## Level 4 — Director

AI 提出：

- Event Proposal；
- Quest Proposal；
- Balance Proposal。

仍需 Validator。

---

## Level 5 — Developer Agent

AI：

- 產生 Adapter；
- 測試；
- Scenario；
- Schema migration；
- Debug report；
- Asset pipeline。

---

# 48. AI 與 ScenarioIR

現有 ScenarioIR 是極重要資產。

AI 生成世界後不能只問：

> 看起來合理嗎？

必須：

```text
AI Draft
↓
Compiler
↓
ScenarioIR
↓
Given / When / Then
↓
Normal Runtime Pipeline
↓
Pass / Fail
```

因此 AI 世界生成可進入：

$$
\boxed{
Generate
\rightarrow
Compile
\rightarrow
Simulate
\rightarrow
Test
\rightarrow
Repair
}
$$

---

# 49. 世界不是 Prompt

非常重要：

> World State 不應只存在 LLM Context。

世界必須存在：

- Runtime Package；
- StateStore；
- Event Log；
- Snapshot；
- Database；
- State Machine；
- Module Contract。

AI Context 只是：

$$
Projection(W_t)
$$

---

# 50. AI Token 與世界規模解耦

只給 AI 需要的世界 Slice：

$$
Context_i
=
Projection(W_t,Actor_i,Task_i)
$$

而不是：

$$
Context_i=W_t
$$

所以：

$$
N_{worldEntities}
\gg
N_{contextEntities}
$$

這讓大型世界與 AI 成本可以解耦。

---

# 51. Sparse Cognitive Operator

大量世界行為仍由 deterministic Runtime 執行。

AI 只處理：

- 高歧義決策；
- 社會互動；
- 談判；
- 長期目標；
- 自由語言；
- 特殊事件。

因此：

$$
N_{worldTicks}
\gg
N_{AIcalls}
$$

---

# 52. Presentation AI

AI 也可以只負責表現：

```text
Semantic State
↓
AI Presentation Adapter
↓
Dialogue / Description / Asset
```

它不需要改世界規則。

這與現有 Narrative 是 Projection 的 Authority Hierarchy 完全一致。

---

# 53. World Package 與 Presentation Package 分離

建議：

```text
build/
├─ world.package.json
└─ presentation/
   ├─ bakin.package.json
   ├─ godot.package.json
   └─ web.package.json
```

World Package：

> 可執行世界真相。

Presentation Package：

> 如何把世界具象化。

---

# 54. 新增 Presentation Contract

建議新增版本化 Schema：

```text
schemas/
├─ engine-capability.v0.1.schema.json
├─ entity-binding.v0.1.schema.json
├─ projection-snapshot.v0.1.schema.json
├─ projection-delta.v0.1.schema.json
├─ presentation-archetypes.v0.1.schema.json
├─ authority-matrix.v0.1.schema.json
└─ engine-event.v0.1.schema.json
```

---

# 55. EngineEvent 契約

Engine 需要回報的不是所有低階細節。

只回報被授權的語義事件。

例如：

```json
{
  "event_type": "engine.combat_hit_confirmed",
  "actor_id": "player.neo",
  "target_id": "npc.bandit.04",
  "payload": {
    "attack_id": "attack.slash.03"
  }
}
```

再由 Combat Module 驗證與計算 persistent consequence。

---

# 56. Capability-aware Projection

如果 Client：

```text
supports_physics = false
```

Runtime 可以投影：

> 直接 room-to-room movement。

如果：

```text
supports_physics = true
```

Runtime 可以允許：

> Physical Navigation Adapter。

同一世界可以支援不同粒度的 Client。

---

# 57. Projection LOD

世界實體可有：

## L0 — Dormant

只保留最小狀態。

## L1 — Coarse Simulation

遠方 NPC：

- Job；
- Income；
- Migration；
- Schedule coarse tick。

## L2 — Regional Simulation

較細關係、經濟、事件。

## L3 — Active Simulation

玩家附近。

## L4 — Embodied

有 EngineObject、動畫、Physics、Audio。

因此：

$$
\boxed{
WorldEntity
\rightarrow
SimulationLOD
\rightarrow
PresentationLOD
}
$$

---

# 58. Active Set Projection

這與既有 Legacy World Virtualization 的 Active-Set Projection 可以統一。

以前是：

> 因為 32-bit legacy game 容量有限，只投影一部分外部世界。

未來則變成更一般的：

> **任何 Client 都只實體化自己需要的 Active Set。**

---

# 59. World Runtime SDK

長期應提供：

```text
CompilableWorld SDK
├─ Session API
├─ Action API
├─ Projection API
├─ Event API
├─ Entity Binding API
├─ Clock API
├─ Snapshot API
├─ Capability API
└─ Diagnostics API
```

---

# 60. Transport

WGBP 不綁定單一 Transport。

可提供：

- in-process API；
- local socket；
- stdio；
- HTTP；
- WebSocket；
- named pipe；
- MCP-compatible read/action gateway；
- future network transport。

語義契約與傳輸層分離。

---

# 61. Security

Engine Client 也不能因為在本機就自動擁有全部權限。

可以使用：

```text
permissions:
  world.observe
  scene.subscribe
  action.submit
  combat.report
  presentation.read
```

高風險：

```text
world.admin
tick.advance
state.repair
snapshot.restore
```

必須分離。

---

# 62. Determinism 與 Replay

世界層要盡可能維持：

$$
W_{t+1}
=
F(W_t,A_t,E_t)
$$

並保存：

- Action provenance；
- Event ordering；
- StateDelta；
- RNG seed；
- Runtime tick。

Renderer 的 FPS 不應影響世界歷史。

---

# 63. Physics Replay 邊界

高頻 Physics 不一定完整進 World Event Log。

可以只提交：

> semantic checkpoints。

例如：

```text
attack started
hit confirmed
damage committed
entity defeated
```

而不是：

> 每個 rigid body transform。

---

# 64. Direct Renderer 的最小 Runtime

未來最小遊戲堆疊可以是：

```text
CompilableWorld
+
Presentation Adapter
+
Renderer
+
Input
+
Audio
```

如果不需要複雜 physics：

> 甚至不需要完整 Game Engine。

---

# 65. Executable World Platform

因此 CompilableWorld 的終局定位不是：

> Another Game Engine

而是：

# **Executable World Platform**

它解決：

> **如何讓世界本身成為可編譯、可執行、可持續、可投影、可被 AI 操作但不被 AI 任意改寫的系統。**

---

# 66. 與傳統 Game Engine 的差異

Game Engine 主要解決：

- Rendering；
- Physics；
- Audio；
- Input；
- Asset Pipeline；
- Scene Runtime。

CompilableWorld 主要解決：

- World State；
- Causality；
- Entity identity；
- State Transition；
- Long-term persistence；
- Economy；
- Society；
- Faction；
- Quest；
- Relationship；
- AI action boundary；
- World history；
- Replay；
- Projection。

因此：

$$
\boxed{
GameEngine
\neq
WorldRuntime
}
$$

---

# 67. 最小 Game Binding Prototype

## CW-WGBP-00

建立：

```text
One Runtime Package
        │
        ├─ Terminal
        ├─ Web
        └─ Game Adapter Prototype
```

三個入口共享：

- StateStore；
- Event Log；
- ActionIR；
- StateDelta；
- EventIR。

---

# 68. 驗收條件

同一個 Action：

```text
talk npc.blacksmith
```

無論從：

- Terminal；
- Web；
- Game Client；

進入，都產生語義等價：

```text
ActionIR
→ same module path
→ same StateDelta
→ same EventIR
```

UI 顯示可以完全不同。

---

# 69. CW-WGBP-01 — Entity Binding

加入：

- stable WorldEntity ID；
- EngineInstance ID；
- generation；
- spawn；
- despawn；
- reconnect。

---

# 70. CW-WGBP-02 — Projection Streaming

加入：

- subscribe；
- unsubscribe；
- snapshot；
- delta；
- LOD。

---

# 71. CW-WGBP-03 — Multi-rate Clock

加入：

- render clock contract；
- gameplay clock；
- world clock；
- clock drift diagnostics。

---

# 72. CW-WGBP-04 — Bakin Adapter

以 Meine-Reise-like 小世界驗證：

- 1 城；
- 30 NPC；
- shop；
- quest；
- schedule；
- faction flag。

---

# 73. CW-WGBP-05 — Godot Adapter

同一個 Runtime Package：

- 用 Godot 3D Scene 呈現；
- 不修改 World Rules。

---

# 74. CW-WGBP-06 — Direct Renderer

至少建立：

> 不依賴 Bakin / Godot 的最小 2D Projection。

驗證：

$$
WorldRuntime
+
Renderer
$$

本身可形成可玩體驗。

---

# 75. CW-MODULE-00 — Module Registry

將世界功能正式 catalog 化：

```text
module_id
version
dependencies
actions
events
read_scope
write_scope
state_schema
projection_schema
authority
```

---

# 76. Module Dependency Graph

例如：

```text
npc.occupation
    ↓
economy.production
    ↓
economy.market
    ↓
quest.dynamic
```

Compiler 應驗證：

- dependency；
- version；
- cycle；
- authority conflict；
- state path conflict。

---

# 77. AI Module Selection

未來 AI 可以根據設計要求：

```text
"我要商業與戰爭，但不要家族系統"
```

生成：

```yaml
enable:
  npc.occupation
  npc.schedule
  economy.production
  economy.market
  faction.core
  diplomacy.core
  war.core

disable:
  npc.family
  inheritance.core
```

---

# 78. World Template

可提供：

```text
templates/
├─ social_sim
├─ crpg
├─ living_world_rpg
├─ city_sim
├─ kingdom_sim
└─ 4x_light
```

但 Template 只是 Module Preset。

不是新的 Runtime。

---

# 79. World Compiler 的長期角色

Compiler 不只是格式轉換器。

它最終應負責：

- schema validation；
- semantic validation；
- dependency resolution；
- authority conflict；
- module binding；
- state reachability；
- action availability；
- presentation mapping；
- scenario validation；
- deployment package。

所以：

$$
\boxed{
WorldCompiler
=
SemanticBuildSystem
}
$$

---

# 80. Studio 的長期角色

EveGlyph / Studio 可以變成：

> World IDE。

視覺化：

- Entity Graph；
- State Machine；
- Faction；
- Economy；
- Relationship；
- Event；
- Module；
- Projection；
- Engine Binding；
- AI Actor。

仍維持：

> Authoring → Review → Compile → Runtime

而不是 UI 直接寫 Runtime State。

---

# 81. MCP 的位置

現有 MCP 研究不應成為另一套世界控制邏輯。

MCP 只是：

```text
AI / Agent
↓
MCP Gateway
↓
ActionIR / Projection
↓
World Runtime
```

所以 MCP 與 Game Engine Adapter 是：

> 同一 Runtime 的不同 Client 類型。

---

# 82. Memory 的位置

AMK：

$$
WorldState/EventLog
\rightarrow
MemoryEvidence
$$

不能：

$$
Memory
\rightarrow
DirectWorldOverride
$$

AI 的記憶與世界事實分離。

這個原則在多 Client / 多 Agent 世界中特別重要。

---

# 83. 世界歷史

Event Log 長期可成為：

```text
World History
├─ political
├─ economic
├─ personal
├─ military
├─ exploration
└─ social
```

再投影：

- 年鑑；
- NPC 回憶；
- Newspaper；
- Quest；
- AI Context；
- Replay。

---

# 84. Long Session

CompilableWorld 已有長 session validation 與 snapshot / replay 基礎。

未來 Game Binding 必須加入長時間測試：

- 10k ticks；
- repeated hydrate/dehydrate；
- Client disconnect/reconnect；
- engine crash；
- Runtime restart；
- snapshot restore；
- duplicate Action；
- stale EntityBinding。

---

# 85. 失敗模式

必須防止：

## Split Brain

Engine 與 Runtime 都認為自己是 Authority。

## Ghost Entity

Engine Object 已消失但 Binding 仍有效。

## Stale Generation

舊 Instance 向新 Entity 寫回資料。

## Double Commit

Engine retry 導致 Action 重複執行。

## Projection Leak

某 Actor 看見不應看見的 private state。

## Clock Drift

Gameplay 與 World Clock 長期不一致。

## Silent Engine Rule

Engine 偷偷執行世界規則但沒有 EventIR。

---

# 86. Fail-closed 原則

當：

- version 不符；
- capability 不符；
- authority 不明；
- binding stale；
- projection generation 錯誤；
- action idempotency 無法確認；

應：

> Fail closed。

不能猜。

---

# 87. Engine Independence Success Criteria

CompilableWorld 真正 Engine-independent 的最低證明：

## Test A

Terminal 與 Web 共用同一 Runtime。

現有 MVP 已成立。

## Test B

新增 Bakin / Game Adapter。

## Test C

新增 Godot Adapter。

## Test D

三者使用同一 Runtime Package。

## Test E

同一測試 Scenario 產生相同世界結果。

如果成立：

$$
\boxed{
WorldLogic
\perp
PresentationEngine
}
$$

---

# 88. Direct Renderer Success Criteria

同一 Runtime Package：

```text
without Godot
without Unity
without Bakin
```

仍可透過最小 Renderer 玩。

這將證明：

> Game Engine 是 Optional Presentation Infrastructure。

---

# 89. 商業／平台化方向

未來其他開發者不一定是：

> 「使用 CompilableWorld 做遊戲。」

而可能是：

> **把自己的 Renderer / Engine / Client 接到 CompilableWorld World Runtime。**

---

# 90. World Runtime as Service

長期甚至可以：

```text
World Server
│
├─ PC RPG Client
├─ Mobile Client
├─ Browser Strategy Client
├─ AI NPC Agent
└─ Admin / Observatory
```

---

# 91. AI-Native Game Creation

最終使用者可能只需要：

> 「我要一個 4 國、800 NPC、低魔世界；有宗教、商業、戰爭、傭兵，但不要家族世代。」

AI：

1. 選 Module；
2. 生成 Authoring；
3. 編譯；
4. 產生 Scenario；
5. 模擬；
6. 修正；
7. 配資產；
8. 綁 Presentation；
9. 啟動。

---

# 92. AI 變得「更無腦」的真正原因

不是 AI 突然不用推理。

而是：

> **大量遊戲設計問題已經被壓縮成標準化世界語義與可重用模組。**

因此 AI 不必每次重新發明：

- Inventory；
- Relationship；
- Economy；
- War；
- Quest；
- NPC Schedule。

而是調用：

```text
inventory.core
relationship.core
economy.market
war.core
quest.dynamic
npc.schedule
```

---

# 93. 從程式重用到世界規則重用

傳統：

$$
CodeReuse
$$

CompilableWorld 長期希望做到：

$$
\boxed{
WorldRuleReuse
}
$$

這是更高層次的軟體積木化。

---

# 94. 最終抽象

可以將整個平台寫為：

$$
\boxed{
ExecutableWorld
=
Modules
+
Entities
+
State
+
Actions
+
Transitions
+
Events
+
Persistence
+
Projection
}
$$

遊戲則是：

$$
\boxed{
Game
=
ExecutableWorld
+
InteractionProfile
+
Presentation
}
$$

---

# 95. 與「世界狀態機」研究主線的關係

本白皮書不把 State Machine 降格成單一 FSM 技術。

State Machine 是：

> **可編譯世界轉移的一個核心表示。**

但完整平台同時需要：

- FunctionIR；
- ActionIR；
- EventIR；
- Module Contract；
- Scheduler；
- Projection；
- Memory boundary；
- Compiler；
- Adapter。

因此最終不是：

> 巨大單一狀態機。

而是：

$$
\boxed{
\text{A composable network of bounded executable state machines and modules}
}
$$

---

# 96. 第一個新里程碑

建議正式建立：

# **CompilableWorld WGBP v0.1**

輸出：

1. `ENGINE_BINDING_CONTRACT_zh-TW.md`
2. `engine-capability.v0.1.schema.json`
3. `entity-binding.v0.1.schema.json`
4. `projection-snapshot.v0.1.schema.json`
5. `projection-delta.v0.1.schema.json`
6. `authority-matrix.v0.1.schema.json`
7. reference `GameAdapter`
8. test FakeEngine Client
9. hydrate / dehydrate tests
10. reconnect / stale-generation tests

---

# 97. 第二個新里程碑

# **CompilableWorld Module Registry v0.1**

先將目前已有：

- exploration；
- combat；
- magic；
- dialogue；
- quest；
- state-machine core；

正式整理成 Module Catalog。

後續再增加：

- occupation；
- economy；
- faction；
- relationship；
- schedule。

---

# 98. 第三個新里程碑

# **Meine-Reise-like Vertical Slice**

使用：

```text
CompilableWorld
+
Bakin Adapter
```

只建立：

- 1 城；
- 30 NPC；
- 5 occupation；
- 1 local market；
- 1 faction；
- schedule；
- relationship；
- quest。

若 Bakin 不適合直接 Runtime Bridge，也可以先以 Web / Mock Adapter 驗證世界，再替換 Presentation。

---

# 99. 第四個新里程碑

# **Same World / Two Engines Test**

同一 Runtime Package：

```text
Bakin Client
Godot Client
```

分別載入同一小世界。

如果：

- NPC identity；
- world state；
- quest；
- relationship；
- economy；

一致，而畫面完全不同：

> Engine-independent World Runtime 得到實證。

---

# 100. 最終願景

CompilableWorld 不只是：

> 「世界狀態機。」

也不只是：

> 「遊戲 Runtime。」

最終目標是：

# **通用可執行世界平台**

其核心價值：

> **把「世界如何存在與變化」從「世界如何被畫出來」中分離。**

因此：

$$
\boxed{
World\neqView
}
$$

$$
\boxed{
World\neqEngine
}
$$

$$
\boxed{
AI\neqWorldAuthority
}
$$

而：

$$
\boxed{
World
=
ExecutableSemanticState
+
BoundedTransitions
+
CausalEvents
+
PersistentHistory
}
$$

---

# 101. 最終公式

CompilableWorld 長期架構：

$$
\boxed{
\text{Authoring}
\rightarrow
\text{World Compiler}
\rightarrow
\text{Executable World Runtime}
\rightarrow
\text{Binding Protocol}
\rightarrow
\text{Any Presentation}
}
$$

而 AI-Native 遊戲製作：

$$
\boxed{
Intent
\rightarrow
ModuleComposition
\rightarrow
WorldGeneration
\rightarrow
Compile
\rightarrow
ScenarioValidation
\rightarrow
PresentationBinding
\rightarrow
PlayableWorld
}
$$

---

# 102. 最終判定

當世界模組足夠多、分類足夠精細、介面足夠穩定後：

> **開發者不必每次重新寫一個世界。**

他們只需要：

1. 選世界模組；
2. 定義內容；
3. 配置規則；
4. 接一個 Presentation；
5. 讓 AI 協助組裝、生成、測試與補全。

因此 CompilableWorld 與 Unity / Godot / Bakin 並不是必然競爭關係。

前者主要回答：

> **世界怎麼活？**

後者主要回答：

> **世界怎麼被呈現與互動？**

而當 Presentation Stack 足夠薄時：

> **CompilableWorld 甚至可以直接連 Renderer，而不需要傳統完整 Game Engine。**

這就是本白皮書所定義的：

# **Executable World Platform**

---

# 附錄 A：現有 MVP 與本白皮書新增範圍

## A.1 現有 MVP 已實作／已有基礎

- Authoring → Compiler → Runtime Package；
- World Kernel；
- ActionIR；
- StateDelta；
- EventIR；
- Atomic Commit；
- Event Log；
- Snapshot / Replay；
- Module Contract；
- Terminal Gateway；
- Web Gateway；
- Studio read-only projection；
- Scoped StateIR；
- Action-scope behavior；
- FunctionIR；
- ScenarioIR；
- MCP / Agent 相關 read/action、安全、協調與 durability 基礎；
- Runtime host authoritative tick；
- AI / MCP 不得直接寫 StateStore。

## A.2 本白皮書新增提案

- WGBP；
- EngineCapability；
- EntityBinding；
- AuthorityMatrix for engines；
- ProjectionSubscription；
- ProjectionSnapshot / Delta；
- EngineEvent；
- Hydration / Dehydration；
- Multi-rate Clock；
- Presentation Semantics；
- Presentation Archetype Registry；
- Bakin Adapter；
- Godot Adapter；
- Direct Renderer Adapter；
- World Module Registry；
- Genre as ModuleSet + Projection + RuleProfile；
- AI World Assembler；
- Same World / Multiple Presentation Runtime。

---

# 附錄 B：設計禁區

第一階段不要：

- 直接把 Renderer 細節塞進 StateStore；
- 讓 Engine 直接改 Quest／Relationship／Economy；
- 讓 AI 直接提交 StateDelta；
- 把完整 World State 塞進 LLM Context；
- 綁死 Godot；
- 綁死 Bakin；
- 為每個 Engine 重寫世界規則；
- 讓 Projection 成為新的 State Authority；
- 用 Physics Tick 當 World Tick；
- 將裸 Engine Pointer 當 World Entity ID；
- 未版本化就建立 Adapter protocol。

---

# 版本紀錄

## v0.1 — 2026-08-10

- 將 CompilableWorld 定位擴張為 Executable World Platform。
- 保留現有 Runtime MVP 的 Kernel / ActionIR / StateDelta / EventIR / Projection 架構。
- 新增 World–Game Binding Protocol 概念。
- 建立 Authority Matrix。
- 分離 Canonical / Engine-local / Shared State。
- 分離 Semantic Position 與 Physical Position。
- 建立 EntityBinding + Generation。
- 建立 Projection Snapshot / Delta。
- 建立 Hydration / Dehydration。
- 建立 Multi-rate Clock。
- 建立 World-authoritative / Subsystem-authoritative Combat 模式。
- 建立 Sidecar-first / Embedded / Server Runtime 模式。
- 建立 Direct Renderer 路線。
- 建立 Presentation Semantics。
- 建立 World Module Registry 與 Genre Composition。
- 將 AI 定義為 World Assembler / Runtime Actor / Director，而非 World Authority。
- 建立 CW-WGBP-00～06 路線。
- 建立 Same World / Two Engines 驗證目標。
