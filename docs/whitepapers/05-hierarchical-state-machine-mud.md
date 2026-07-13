---
title: "Ultra-Large-Scale Hierarchical Finite-State-World MUD: AI-Driven Composite Behavior, Event Transduction, and Compilable World State Machines"
subtitle: "From Traditional Text Commands to Natural-Language Action IR, Hierarchical State Machines, and Event-Sourced Worlds"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "Technical Architecture Paper Draft"
translated_from: "超大型階層式有限狀態世界MUD_AI驅動複合行為與事件轉導架構_v0.1.md"
date: "2026-07-13"
language: "en-US"
keywords:
  - MUD
  - Finite State Machine
  - Hierarchical State Machine
  - Action IR
  - Event IR
  - CompilableWorld
  - AI Agent
  - Event Sourcing
  - World State Machine
  - Natural Language Interface
---

# Ultra-Large-Scale Hierarchical Finite-State-World MUD: AI-Driven Composite Behavior, Event Transduction, and Compilable World State Machines

## Abstract

This paper proposes a game architecture that transcends the traditional MUD command model: natural language as the player input interface, AI as the intent-parsing and behavior compiler, and a hierarchical, composable, event-driven finite-state world as the true execution core.

Traditional MUDs rely primarily on combinations of a limited set of verbs and targets, such as `look`, `get sword`, `kill goblin`. This model is stable and cheap to parse, but it has clear limitations: it cannot express multi-step, conditional, covert, cooperative behaviors with timing requirements. The system proposed in this paper allows players to describe higher-complexity intent using natural language, for example:

> Pretend not to notice the guard, slowly approach the door, wait until he turns away, then use your left hand to retrieve the key hidden in your clothes and try to open the door silently.

The AI does not directly determine the outcome; instead, it converts this natural-language input into a constrained, verifiable, schedulable Action IR. A deterministic rule engine then executes the actual state transitions based on character state, world state, items, time, environment, and conflict rules.

The overall pipeline is:

$$
T_{\mathrm{player}}
\xrightarrow{\mathcal{P}}
A_{\mathrm{IR}}
\xrightarrow{\mathcal{V}}
A_{\mathrm{valid}}
\xrightarrow{\mathcal{S}}
A_{\mathrm{scheduled}}
\xrightarrow{\mathcal{T}}
\Delta W
\xrightarrow{\mathcal{E}}
E
\xrightarrow{\mathcal{N}}
T_{\mathrm{result}}
$$

Where:

- $T_{\mathrm{player}}$: the player's natural-language input;
- $\mathcal{P}$: AI intent parsing and behavior compilation;
- $A_{\mathrm{IR}}$: structured behavior intermediate representation;
- $\mathcal{V}$: precondition and rule validation;
- $\mathcal{S}$: behavior scheduling;
- $\mathcal{T}$: state transition;
- $\Delta W$: world state delta;
- $E$: set of events;
- $\mathcal{N}$: narrative output generation.

This paper argues that a truly workable architecture is not one giant monolithic FSM, but a hierarchical cluster of state machines operating at world, region, scene, entity, system, and action levels. These state machines cooperate through an event bus, state deltas, priority ordering, and conflict-resolution strategies.

Ultimately, the MUD is no longer merely a text-command game, but becomes a large compilable world state machine operated through a text interface.

**Keywords:** MUD, Finite State Machine, Hierarchical State Machine, Action IR, Event Sourcing, CompilableWorld, AI Agent, Natural-Language Behavior, World State Machine

---

# Chapter 1  Problem Statement

## 1.1 The Ceiling of the Traditional MUD Command Model

Traditional MUDs typically adopt the form:

```text
verb
verb target
verb target with instrument
```

For example:

```text
look
get sword
open door
attack goblin
unlock door with key
```

Commands of this kind are unambiguous, easy to parse, and cheap — but they also carry clear limitations:

1. Behavior is usually compressed into a single step;
2. There is no notion of timing;
3. There is no support for conditional waiting;
4. There is no support for parallel actions;
5. There is no notion of manner/method;
6. There is no social meaning;
7. There is no distinction between intent and appearance;
8. Composite operations are hard to express;
9. High-freedom player strategy is difficult to support.

For example:

```text
open door
```

cannot express:

- opening the door slowly;
- opening the door silently;
- pretending to walk past before opening it;
- waiting for the guard to turn away before opening it;
- opening the door in sync with a companion;
- freezing the lock brittle before opening it;
- bracing the door with your body to prevent it being locked from the other side.

---

## 1.2 AI Makes Natural-Language Behavior Compilation Possible

In the past, if players were allowed to freely describe behavior, the system would struggle to parse it reliably.

But with the emergence of AI, we can now build:

$$
\mathcal{L}_{\mathrm{natural}}
\xrightarrow{\mathrm{AI}}
\mathcal{A}_{\mathrm{finite}}
$$

Where:

- $\mathcal{L}_{\mathrm{natural}}$ is the open-ended natural-language space;
- $\mathcal{A}_{\mathrm{finite}}$ is a finite, verifiable space of behavior primitives.

The role of AI is not to make the rules infinite, but to compress infinite expression into finite operations.

---

## 1.3 The Core Problem

The core problem this paper addresses is:

> How can players be allowed to describe complex behavior using highly free natural language, while the world still maintains finite, verifiable, replayable, and testable state transitions?

---

# Chapter 2  Formal Positioning

## 2.1 Not a Monolithic Giant FSM

If all states across the entire world are directly combined into a single finite state machine, the system will face state explosion.

Suppose a character has:

- 10 body-posture states;
- 8 psychological states;
- 6 combat states;
- 12 social states;
- 20 quest states;
- 50 locations;
- 5 legal states.

Then the theoretical number of combinations is:

$$
10
\times
8
\times
6
\times
12
\times
20
\times
50
\times
5
=
28{,}800{,}000
$$

And this does not even include items, skills, time, weather, factions, or other characters.

Therefore, all combined states cannot be enumerated in advance.

---

## 2.2 Correct Positioning

This system should be defined as:

> An AI-driven, hierarchical, composable, event-sourced world-state-machine MUD.

In English:

> AI-Driven Hierarchical Composable World State Machine MUD

Its ontology is:

$$
\mathcal{W}
=
(
\mathcal{M},
\mathcal{A},
\mathcal{R},
\mathcal{E},
\mathcal{P},
\mathcal{H}
)
$$

Where:

- $\mathcal{M}$: the set of state machines;
- $\mathcal{A}$: the set of behaviors;
- $\mathcal{R}$: transition rules;
- $\mathcal{E}$: the set of events;
- $\mathcal{P}$: priority and conflict policy;
- $\mathcal{H}$: event history and state provenance.

---

# Chapter 3  Hierarchical World State Machines

## 3.1 World Layering

The world state machine is divided into:

$$
\mathcal{M}
=
\{
M_{\mathrm{world}},
M_{\mathrm{region}},
M_{\mathrm{scene}},
M_{\mathrm{entity}},
M_{\mathrm{system}},
M_{\mathrm{action}}
\}
$$

---

## 3.2 World-Level State Machine

Manages:

- world eras;
- global catastrophes;
- climate phases;
- large-scale wars;
- world laws;
- tides of magic;
- technology phases;
- global events.

Example:

```yaml
world_state:
  era: post_cataclysm
  climate_phase: black_winter
  global_war: dormant
  magic_density: rising
```

---

## 3.3 Region-Level State Machine

Manages:

- regional control;
- danger;
- resources;
- population;
- economy;
- epidemics;
- factional influence;
- regional events.

```yaml
region_state:
  controller: gray_crown_guard
  danger_level: 4
  food_supply: 0.42
  unrest: 0.61
  plague_stage: latent
```

---

## 3.4 Scene-Level State Machine

Manages:

- room visibility;
- door/window state;
- fire;
- lighting;
- sound;
- object placement;
- traps;
- area lockdowns.

---

## 3.5 Entity-Level State Machine

Players, NPCs, items, and interactable entities all possess multiple parallel state regions.

```yaml
entity_state:
  posture: standing
  locomotion: stationary
  consciousness: awake
  health: wounded
  combat: guarded
  emotion: suspicious
  legal_status: wanted
  social_role: guest
  equipment_mode: sword_drawn
```

This structure can be expressed as:

$$
S_{\mathrm{entity}}
=
\bigoplus_{i=1}^{n} S_i
$$

Where $\bigoplus$ denotes multiple orthogonal or semi-independent state regions, rather than a pre-enumerated Cartesian product.

---

## 3.6 System-Level State Machines

Independent systems include:

- combat;
- quests;
- economy;
- dialogue;
- factions;
- law;
- sound;
- lighting;
- weather;
- crafting;
- survival;
- reputation.

Systems cooperate through events rather than directly modifying each other's internal state.

---

# Chapter 4  State IR

## 4.1 Definition

State IR is the unified intermediate representation for all world state.

Every State Definition should include:

```text
State ID
Owner Type
Region
Allowed Values
Initial Value
Transition Policy
Persistence
Visibility
Authority
Dependencies
```

---

## 4.2 Example

```yaml
state_definition:
  id: entity.posture
  owner_type: character

  values:
    - standing
    - sitting
    - kneeling
    - prone
    - unconscious

  initial: standing

  persistence: runtime

  transitions:
    standing:
      - sitting
      - kneeling
      - prone
    sitting:
      - standing
      - prone
```

---

## 4.3 State Visibility

Different states carry different visibility levels:

```text
public
observable
inferred
private
system_only
```

For example:

- posture is public;
- whether one is injured can be observed;
- psychological suspicion can only be inferred;
- quest flags are private;
- internal AI scheduling is system-only.

---

# Chapter 5  Action IR

## 5.1 Behavior Is Not a String

Player input:

> Wait until the guard turns away, then use the key hidden in your clothes to open the door silently.

The AI should convert this into:

```yaml
action_sequence:
  actor: player_001

  steps:
    - action: wait_for
      condition:
        target: guard_001
        field: facing
        operator: not_equal
        value: player_001

    - action: retrieve
      target: key_old_vault
      source: clothing_inner
      hand: left
      concealment: true

    - action: unlock
      target: door_014
      instrument: key_old_vault
      mode: silent
```

---

## 5.2 The Formal Structure of Action IR

$$
A
=
(
\alpha,
v,
\tau,
\iota,
\mu,
\theta,
\pi,
\kappa,
\epsilon,
\phi
)
$$

Where:

- $\alpha$: Actor;
- $v$: Verb;
- $\tau$: Target;
- $\iota$: Instrument;
- $\mu$: Method;
- $\theta$: Timing;
- $\pi$: Preconditions;
- $\kappa$: Costs;
- $\epsilon$: Effects;
- $\phi$: Failure Effects.

---

## 5.3 Action Primitives

The underlying layer should retain a finite set of primitives:

```text
move
observe
wait
hold
release
apply_force
damage
heal
unlock
open
close
hide
reveal
speak
deceive
trade
equip
use
combine
cast
coordinate
```

Composite behaviors are composed from these primitives.

---

# Chapter 6  The Behavior Compilation Pipeline

## 6.1 Natural-Language Parsing

```text
Player utterance
→ Intent
→ Behavior candidates
→ Entity resolution
→ Timing resolution
→ Method resolution
→ Action IR
```

---

## 6.2 Handling Ambiguity

If the player says:

```text
open it
```

the system may need to resolve:

- which target?
- using a hand or a tool?
- normally or silently?
- should it move to the target first?

The AI may propose candidate completions, but must not fabricate high-risk intent.

---

## 6.3 Validation

The Action Validator checks:

- whether the Actor exists;
- whether the Target is visible;
- whether the Instrument is held;
- whether the distance is sufficient;
- whether the character's state permits it;
- whether resources are sufficient;
- whether the behavior is forbidden by the environment;
- whether it violates a world axiom;
- whether further decomposition is required.

---

# Chapter 7  Transition Rules

## 7.1 Form

A transition rule is expressed as:

$$
r:
(S,A,C)
\rightarrow
(S',E,O)
$$

Where:

- $S$: the original state;
- $A$: the behavior;
- $C$: conditions and context;
- $S'$: the new state;
- $E$: events;
- $O$: direct output.

---

## 7.2 Example

```yaml
rule:
  id: unlock_door_with_key

  when:
    action.type: unlock
    target.type: door
    instrument.type: key

  require:
    - actor.has(instrument)
    - target.locked == true
    - instrument.key_code == target.lock_code

  effects:
    - set target.locked = false

  emit:
    - door_unlocked
```

---

## 7.3 Failure Rules

```yaml
failure:
  when:
    - actor.skill.lockpicking < target.difficulty

  effects:
    - action.state = failed
    - target.alert_level += 1

  emit:
    - lockpick_failed
    - noise_generated
```

---

# Chapter 8  Event IR

## 8.1 Events Are the Cross-System Cooperation Interface

A door being opened is not merely a boolean flag flipping.

```yaml
event:
  id: event_184220
  type: door_opened
  actor: player_001
  target: door_014
  method: hidden_key
  location: corridor_003
  sound_level: 2
  visibility: local
  legal_status: trespassing
  timestamp: 184220
```

---

## 8.2 Subscribers

```text
Door System
Sound System
Guard AI
Law System
Quest System
Narrative Renderer
Audit Log
```

---

## 8.3 Event Sourcing

World state can be reconstructed from a Snapshot plus events:

$$
W_t
=
\operatorname{Fold}
(
W_{t_0},
E_{t_0+1},
\ldots,
E_t
)
$$

This allows for:

- replay;
- rollback;
- debugging;
- AI player analysis;
- world branching;
- causal tracing.

---

# Chapter 9  The State Machine of Behavior Itself

## 9.1 Composite Behavior Has a Lifecycle

```text
proposed
→ parsed
→ validated
→ queued
→ executing
→ interrupted
→ resumed
→ completed
→ failed
→ cancelled
```

---

## 9.2 Long-Duration Behavior

Applicable to:

- lockpicking;
- healing;
- forging;
- spellcasting;
- reading;
- searching;
- negotiating;
- long-distance travel.

```yaml
action_instance:
  id: pick_lock_001
  state: executing
  duration: 8
  progress: 3

  interrupt_when:
    - actor.takes_damage
    - target.moves
    - actor.tool_missing
    - actor.concentration < 20
```

---

# Chapter 10  Concurrency, Conflict, and Priority

## 10.1 Simultaneous Conflicts

At the same time, the following may all occur:

- a player closing a door;
- an NPC opening a door;
- fire destroying the door;
- an explosion breaking a wall;
- a quest event locking down the area.

Therefore, the system cannot rely on an arbitrary execution order.

---

## 10.2 Conflict Policy

The following must be defined:

- Priority;
- Atomicity;
- Lock;
- Interrupt;
- Rollback;
- Merge;
- Last-Writer;
- Domain Authority.

---

## 10.3 Example

```yaml
conflict_policy:
  resource: door_014

  precedence:
    destruction: 100
    system_lock: 80
    close: 40
    open: 40

  tie_breaker:
    - initiative
    - timestamp
    - actor_id
```

---

## 10.4 State Deltas

All behavior first produces a Delta:

```yaml
delta:
  target: door_014
  field: state
  from: closed
  to: open
  authority: player_action
  priority: 40
```

which is then submitted for final commit by the conflict resolver.

---

# Chapter 11  Narrative Output

## 11.1 Separating Rule Outcomes from Text

Underlying result:

```yaml
result:
  success: true
  events:
    - door_unlocked
    - door_opened
    - low_noise_generated
```

The narrative layer may output:

> You wait until the guard turns away, then quietly draw the key hidden inside your clothes. The bolt gives a soft click, and the door slides open a silent crack.

---

## 11.2 Narrative Must Not Rewrite Outcomes

The Narrative Renderer may only express already-determined results; it must not, on its own:

- add items;
- alter damage;
- claim an NPC failed to notice something;
- add quest success;
- rewrite world axioms.

---

# Chapter 12  The Expansion of CompilableWorld

## 12.1 Not Just Compiling World Data

A complete CompilableWorld should comprise:

$$
\mathrm{CompilableWorld}
=
D
+
S
+
A
+
T
+
E
+
P
+
H
$$

Where:

- $D$: world data;
- $S$: state definitions;
- $A$: behavior definitions;
- $T$: transition rules;
- $E$: event contracts;
- $P$: priority and conflict policy;
- $H$: history and event-sourcing rules.

---

## 12.2 Division of Labor Among JSON / CSV / EML

```text
CSV: bulk state values, behavior parameters, skills, items, rooms
JSON: nested rules, events, quests, state machines
EML: high-density semantics, conditions, transitions, lifecycles, patches
```

---

# Chapter 13  The Boundaries of AI's Responsibility

## 13.1 What AI May Do

- natural-language parsing;
- behavior candidate generation;
- target and tool resolution;
- composite behavior decomposition;
- low-risk parameter completion;
- narrative output;
- test strategy;
- error analysis.

---

## 13.2 What AI Must Not Do Directly

- unilaterally decide high-risk success;
- skip preconditions;
- rewrite world axioms;
- write directly to authoritative state;
- resolve conflicts on its own;
- approve code changes on its own;
- fabricate nonexistent facts to suit the narrative.

---

# Chapter 14  The Five Core Specifications the First Version Must Complete

## 14.1 State IR

Defines:

- world;
- region;
- scene;
- entity;
- system;
- action.

---

## 14.2 Action IR

Defines:

- Actor;
- Verb;
- Target;
- Instrument;
- Method;
- Timing;
- Preconditions;
- Costs;
- Effects;
- Failure.

---

## 14.3 Transition Rule

Defines:

$$
(S,A,C)
\rightarrow
(S',E)
$$

---

## 14.4 Event IR

Defines all cross-system notifications.

---

## 14.5 Conflict Resolution

Defines:

- Priority;
- Atomicity;
- Interrupt;
- Rollback;
- Merge;
- Tie Breaker.

---

# Chapter 15  MVP Roadmap

## Phase 0: Minimal State Core

Supports only:

- posture;
- location;
- doors;
- held items;
- basic hit points;
- behavior scheduling.

---

## Phase 1: Action IR

Initially supports:

```text
move
observe
take
drop
open
close
unlock
wait
attack
speak
```

---

## Phase 2: Composite Behavior

Supports:

- Sequential;
- Conditional;
- Wait;
- Interrupt;
- Retry;
- Cancel.

---

## Phase 3: Event System

Adds:

- sound;
- visibility;
- law;
- quests;
- NPC reactions.

---

## Phase 4: AI Natural-Language Compilation

AI only converts natural language into Action IR; it does not execute directly.

---

## Phase 5: Multi-Agent and Large-Scale World

Adds:

- multiple players;
- NPC Agents;
- AI test players;
- regional state machines;
- world-level events.

---

# Chapter 16  Testing Strategy

## 16.1 Action IR Testing

- command parsing;
- ambiguity;
- missing parameters;
- nonexistent targets;
- invalid tools;
- precondition failure.

---

## 16.2 Transition Testing

- success;
- failure;
- interruption;
- rollback;
- concurrency;
- race conditions.

---

## 16.3 Event Testing

- subscription;
- duplicate events;
- ordering;
- loss;
- replay;
- Snapshot restoration.

---

## 16.4 AI Testing

- synonymous phrasing;
- compound sentences;
- deliberate ambiguity;
- malicious privilege escalation;
- narrative-induced manipulation;
- nonexistent capabilities.

---

# Chapter 17  Anti-Patterns

## 17.1 A Monolithic Giant FSM

Combining all states together causes state explosion.

## 17.2 AI Directly Adjudicating Outcomes

This destroys replayability and testability.

## 17.3 Behavior Directly Mutating State

This lacks events, auditing, and cross-system cooperation.

## 17.4 The Narrative Layer Deciding the Rules

Text generation must not rewrite the world's true state.

## 17.5 All Behavior Completing Instantaneously

This loses interruption, timing, and strategy.

## 17.6 No Conflict Resolution

Multiplayer and multi-agent worlds will produce non-reproducible results.

---

# Chapter 18  Theoretical Significance

## 18.1 The MUD Becomes a World Operation Interface

The MUD is no longer merely a game genre; it becomes:

> A natural-language interface for operating a large-scale world state machine.

---

## 18.2 AI Becomes a Language Compiler

The core role of AI is not to freely write stories, but to perform:

$$
\text{Natural Language}
\rightarrow
\text{Finite Action Space}
$$

---

## 18.3 The World Becomes a Computable State History

The world is no longer just a map and text; it is:

$$
W_t
=
W_0
+
\sum_{i=1}^{t}\Delta W_i
$$

and every $\Delta W_i$ is traceable back to a behavior and its events.

---

# Chapter 19  Conclusion

This paper proposes an ultra-large-scale hierarchical finite-state-world MUD.

Its core is not about writing longer text descriptions, nor about letting AI arbitrarily decide game outcomes — it is about building the following closed loop:

```text
Natural language
→ AI behavior compilation
→ Action IR
→ Validation
→ Scheduling
→ Hierarchical state machines
→ Events
→ World delta
→ Narrative output
```

The true ontology of the system is:

> A set of composable, concurrent, interruptible, rollback-capable, event-sourced world state machines.

AI allows players to express themselves with highly free language, while the underlying layer still maintains finite behavior primitives and deterministic rules.

Therefore, this project is not merely a typical MUD, but:

> An AI-driven, natural-language-compilable world-state-machine game.

---

# Appendix A  Minimal Action IR

```yaml
action:
  id: action_001
  actor: player_001
  verb: unlock
  target: door_014
  instrument: key_old_vault
  method:
    stealth: true
    hand: left
  timing:
    after:
      condition: guard_001.facing != player_001
  preconditions:
    - actor.has(instrument)
    - actor.distance(target) <= 1
  cost:
    stamina: 1
  success:
    - target.locked = false
  failure:
    - emit noise_generated
```

---

# Appendix B  Minimal Event IR

```yaml
event:
  id: event_001
  type: door_unlocked
  source_action: action_001
  actor: player_001
  target: door_014
  location: corridor_003
  timestamp: 184220
  visibility: local
  sound_level: 1
  subscribers:
    - door_system
    - guard_ai
    - law_system
    - quest_system
    - narrative_renderer
```

---

# Appendix C  First-Version Implementation Checklist

- [ ] State IR Schema
- [ ] Action IR Schema
- [ ] Event IR Schema
- [ ] Transition Rule Schema
- [ ] Conflict Policy Schema
- [ ] Action Parser
- [ ] Action Validator
- [ ] Action Scheduler
- [ ] State Store
- [ ] Event Bus
- [ ] Delta Committer
- [ ] Narrative Renderer
- [ ] Snapshot
- [ ] Event Log
- [ ] Replay
- [ ] AI Natural Language Adapter
- [ ] AI Player Test Suite
