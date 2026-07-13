---
title: "CompilableWorld's Pre-Authoring Data Layer: JSON, CSV, Manifest, and a Maintainable World Data Architecture"
subtitle: "From Human–AI Co-Authored Data to a Verifiable, Compilable, Portable World Source Layer"
author: "Neo.K / EVEMISSLAB"
version: "v0.1"
status: "Technical Architecture Draft"
date: "2026-07-13"
translated_from: "CompilableWorld前置資料層_JSON_CSV_Manifest與可維護世界資料架構_v0.1.md"
language: "en-US"
keywords:
  - CompilableWorld
  - JSON
  - CSV
  - World IR
  - EML
  - Manifest
  - Schema
  - AI Agent
  - Evennia
  - Data Authoring
---

# CompilableWorld's Pre-Authoring Data Layer: JSON, CSV, Manifest, and a Maintainable World Data Architecture

## Abstract

This paper proposes a technical architecture in which, both before CompilableWorld is formally completed and after, JSON, CSV, and Manifest should be retained as a world source layer that humans and AI can jointly maintain.

CompilableWorld's goal is to transform heterogeneous data — novels, world-setting definitions, rules, characters, maps, quests, economies, and events — into a world structure that is verifiable, compilable, executable, versionable, and portable. However, if humans and AI operate directly on the final Runtime IR, underlying database objects, or engine-internal classes, this leads to reduced data readability, a higher maintenance barrier, difficulty performing batch modifications, rigid format evolution, and confusion between source data and execution state.

This paper therefore argues:

> JSON and CSV should not be treated as a temporary stand-in used only until CompilableWorld is complete; they should be formally positioned as the Authoring Layer — the source data layer that humans and AI jointly edit, review, batch-process, and version-control.

The overall architecture is as follows:

$$
T_{\mathrm{natural}}
\rightarrow
A_{\mathrm{JSON/CSV}}
\rightarrow
N_{\mathrm{normalized}}
\rightarrow
V_{\mathrm{validated}}
\rightarrow
W_{\mathrm{IR}}
\rightarrow
C_{\mathrm{world}}
\rightarrow
R_{\mathrm{runtime}}
$$

Where:

- $T_{\mathrm{natural}}$: novels, setting documents, prompts, and manual input;
- $A_{\mathrm{JSON/CSV}}$: maintainable source data;
- $N_{\mathrm{normalized}}$: normalized data;
- $V_{\mathrm{validated}}$: data that has passed structural, type, dependency, and rule validation;
- $W_{\mathrm{IR}}$: World Intermediate Representation;
- $C_{\mathrm{world}}$: the CompilableWorld compilation output;
- $R_{\mathrm{runtime}}$: Evennia, the Rust Runtime, a browser-based world, or another target engine.

This paper further defines the respective responsibilities of JSON, CSV, Manifest, Schema, the database, CompilableWorld, and the Runtime, so that the same data never becomes a "source of truth" in more than one place at once. It also proposes specifications for ID namespaces, source tracking, data hashing, compilation ordering, error isolation, version migration, and AI-driven batch maintenance.

**Keywords:** CompilableWorld, JSON, CSV, Manifest, World IR, EML, AI Agent, Data Source Layer, Version Control, World Compilation

---

# Chapter 1  Problem Statement

## 1.1 CompilableWorld Cannot Be Directly Equated with a Human-Editable Format

CompilableWorld should ultimately serve:

- World validation;
- Cross-engine compilation;
- Runtime loading;
- Rule dependencies;
- Save-file migration;
- AI-driven world modification;
- Multi-version world governance.

But this does not mean CompilableWorld's internal format is suitable for direct human maintenance.

The underlying executable format typically exhibits:

- High degrees of normalization;
- Large numbers of reference IDs;
- Compiler-only fields;
- Caches;
- Indexes;
- Engine-capability mappings;
- Internal version metadata;
- Verbose type tags;
- Serialization structures unsuited to manual editing.

If humans and AI operate directly on this layer, editing the world becomes equivalent to directly modifying compiled output.

This is analogous to directly editing a binary file or a database's internal indexes — not a reasonable approach for long-term maintenance.

## 1.2 Requirements That Naturally Emerge in Practice

When actually building a world, developers quickly discover that:

- Large numbers of characters are well suited to tables;
- Large numbers of items are well suited to tables;
- Skill values need batch comparison;
- Map rooms require large numbers of IDs;
- Quests and axioms require nested structures;
- World sources need to preserve human-authored annotations;
- AI needs to be able to batch-generate and batch-correct content;
- Git diffs must remain readable;
- Non-programmer contributors need to participate.

A single format therefore cannot satisfy all of these requirements at once.

Mixing JSON and CSV is not an architectural compromise — it is an acknowledgment of the differences between data shapes.

---

# Chapter 2  Formal Positioning: The Authoring Layer

## 2.1 Definition

This paper defines the JSON/CSV source layer as:

> The world-data editing layer that sits between natural-language sources and CompilableWorld's intermediate representation, jointly operated on by humans, AI, editors, version control, and batch tooling.

Formally:

$$
A_W
=
J_W
\cup
C_W
\cup
M_W
\cup
S_W
$$

Where:

- $J_W$: JSON structured data;
- $C_W$: CSV tabular data;
- $M_W$: Manifest and source index;
- $S_W$: Schema and contracts.

## 2.2 Authoring Format vs. Canonical Runtime Format

The following should be clearly distinguished:

### Authoring Format

For editing by humans and AI:

```text
JSON
CSV
Markdown
EML
Manifest
```

### Canonical Intermediate Format

For validation and compilation:

```text
Normalized World IR
Typed Graph
Resolved References
Validated Rules
```

### Runtime Format

For game execution:

```text
Evennia Objects
Database Rows
Compiled Rust Structures
Runtime Cache
Event State
```

Therefore:

$$
A_W
\neq
W_{\mathrm{IR}}
\neq
R_W
$$

But the three are connected through explicit transformation functions:

$$
f_{\mathrm{normalize}}
:
A_W
\rightarrow
W_{\mathrm{IR}}
$$

$$
f_{\mathrm{compile}}
:
W_{\mathrm{IR}}
\rightarrow
R_W
$$

---

# Chapter 3  The Scope of JSON's Responsibility

## 3.1 Data Suited to JSON

JSON is well suited to representing data with the following properties:

- Nested;
- Optional fields;
- Irregular structure;
- Requires metadata;
- Requires provenance;
- Has multi-level relationships;
- Requires conditions or a state machine;
- Does not flatten well into a table.

Recommended content types for JSON:

```text
world.json
manifest.json
axioms.json
relations.json
quests.json
events.json
factions.json
rule_sets.json
generation_profiles.json
version_map.json
```

## 3.2 The World Master File

```json
{
  "world_id": "black_tide",
  "title": "黑潮之城",
  "version": "0.1.0",
  "schema_version": "0.1.0",
  "genre": [
    "dark_fantasy",
    "political"
  ],
  "default_language": "zh-TW",
  "axiom_files": [
    "axioms/core.json"
  ],
  "source_manifest": "manifest.json"
}
```

## 3.3 Quests Are Well Suited to JSON

Quests typically have state, conditions, and branches:

```json
{
  "quest_id": "quest_black_tide_001",
  "title": "黑潮前兆",
  "states": [
    "unavailable",
    "available",
    "accepted",
    "completed",
    "failed"
  ],
  "requirements": {
    "character_level_min": 2,
    "required_flags": [
      "met_south_gate_guard"
    ]
  },
  "branches": [
    {
      "when": "player.faction == 'guard'",
      "next": "guard_route"
    },
    {
      "when": "player.faction == 'cult'",
      "next": "cult_route"
    }
  ]
}
```

Forcing this into CSV would produce large numbers of duplicated columns, nested JSON strings, condition columns that are hard to read, and would lose the advantages a table is supposed to provide.

---

# Chapter 4  The Scope of CSV's Responsibility

## 4.1 Data Suited to CSV

CSV is well suited to:

- Large volumes of uniformly-shaped data;
- Fixed columns;
- Numeric balancing;
- Manual batch editing;
- Spreadsheet operations;
- Sorting and filtering;
- Translation;
- Managing large numbers of IDs.

Recommended content types for CSV:

```text
characters.csv
items.csv
skills.csv
rooms.csv
exits.csv
loot_tables.csv
recipes.csv
shops.csv
localization.csv
balance_parameters.csv
```

## 4.2 The Character Table

```csv
character_id,name,role,faction,region,level,unique,persistence
npc_guard_001,沉默守衛,guard,gray_crown_guard,gray_crown,3,true,persistent
npc_merchant_001,雜貨商,merchant,civilian,gray_crown,1,false,regenerable
npc_refugee_001,流亡者,refugee,none,south_camp,1,false,delta
```

This format makes it easy to sort in a spreadsheet, bulk-duplicate rows, have AI batch-generate entries, manually check for missing fields, tune values, and perform translation.

## 4.3 Rooms and Exits Should Be Split into Separate Tables

`rooms.csv`:

```csv
room_id,name,region,description_key,danger_level,persistence
room_south_gate,灰冠城南門,gray_crown,room.south_gate.desc,1,persistent
room_market,灰冠市集,gray_crown,room.market.desc,1,persistent
```

`exits.csv`:

```csv
exit_id,from_room,to_room,direction,bidirectional,condition
exit_001,room_south_gate,room_market,north,true,
exit_002,room_market,room_hidden_vault,down,false,has_key:old_vault_key
```

This is far better suited to batch-maintaining a large map than repeating exit definitions inside every room's JSON.

---

# Chapter 5  Manifest: The Master Index of World Data

## 5.1 Why a Manifest Is Necessary

When data is scattered across many JSON and CSV files, the system needs a single point of entry.

The Manifest is responsible for answering:

- Which files belong to this world?
- Which Schema does each file use?
- What is the compilation order?
- What is the ID namespace?
- What is the target Runtime?
- Which modules are depended on?
- Which files are optional?
- What is the hash of each file?
- Which sources were AI-generated?
- Which sources have been human-reviewed?

## 5.2 A Sample Manifest

```json
{
  "world_id": "black_tide",
  "world_version": "0.1.0",
  "schema_version": "0.1.0",
  "namespace": "bt",
  "compiler_version": "0.1.0",
  "targets": [
    "evennia"
  ],
  "sources": {
    "world": "world.json",
    "axioms": [
      "axioms/core.json"
    ],
    "characters": [
      "data/characters.csv"
    ],
    "items": [
      "data/items.csv"
    ],
    "rooms": [
      "maps/rooms.csv"
    ],
    "exits": [
      "maps/exits.csv"
    ],
    "quests": [
      "quests/main_quests.json"
    ],
    "localization": [
      "localization/zh-TW.csv"
    ]
  },
  "dependencies": [
    {
      "module": "core-combat",
      "version": ">=0.1,<1.0"
    }
  ],
  "build": {
    "strict": true,
    "fail_on_warning": false
  }
}
```

## 5.3 The Manifest Is the Sole Compilation Entry Point

The compiler should not scan an entire directory at will and guess which files to load.

It should instead follow:

```text
manifest.json
→ Resolve Sources
→ Validate Paths
→ Validate Hashes
→ Load Schemas
→ Normalize
→ Compile
```

Only this way can the process be reproducible, auditable, versionable, wired into CI, and subject to security constraints.

---

# Chapter 6  Schema and Data Contracts

## 6.1 JSON Schema

JSON should be validated against a Schema for:

- Required fields;
- Types;
- Enums;
- ID format;
- Numeric bounds;
- Nested structure;
- Restrictions on extra fields.

## 6.2 CSV Schema

CSV also needs a formal Schema, rather than relying on column names alone.

```yaml
table: characters
version: 0.1.0

columns:
  character_id:
    type: string
    required: true
    pattern: "^npc_[a-z0-9_]+$"

  level:
    type: integer
    min: 1
    max: 100

  unique:
    type: boolean

  persistence:
    type: enum
    values:
      - persistent
      - delta
      - regenerable
```

## 6.3 Validation Levels

### L1: Syntax Validation

- Whether the JSON is well-formed;
- Whether the CSV is parseable;
- Whether the encoding is correct;
- Whether headers are duplicated.

### L2: Schema Validation

- Fields;
- Types;
- Enums;
- Ranges;
- Formats.

### L3: Reference Validation

- Whether the room exists;
- Whether the NPC's faction exists;
- Whether quest items exist;
- Whether exit destinations exist.

### L4: Semantic Validation

- World-axiom conflicts;
- Quests that cannot be completed;
- Unreachable map areas;
- Infinite economic loops;
- Rules that override one another.

### L5: Target-Capability Validation

- Whether Evennia supports it;
- Whether FluffOS requires special compilation;
- Whether the Rust Runtime has a corresponding type;
- Whether the target engine lacks some piece of semantics.

---

# Chapter 7  A Single Source of Truth

## 7.1 There Must Not Be Multiple Sources of Truth

The most dangerous state is when the same character exists simultaneously in:

- `characters.csv`
- `characters.json`
- PostgreSQL
- Evennia Object
- AI memory
- EML files

and every one of these locations can be modified.

This produces:

$$
D_{\mathrm{conflict}}
=
\sum_{i \neq j}
\operatorname{Diff}(D_i,D_j)
$$

## 7.2 Recommended Division of Responsibility

```text
CSV: large volumes of flat, definitional data
JSON: structured world and rule data
Manifest: source index and compilation entry point
EML: high-density semantics and a front end for rules
World IR: the single normalized compilation contract
Database: runtime state
Runtime Object: current in-memory state
```

## 7.3 Source-of-Truth Rules

### Design Phase

The Authoring Layer is the source of truth.

### Compilation Phase

The Validated World IR is the source of truth.

### Execution Phase

The Runtime Database is the source of current state.

### Update Phase

World-definition changes go back through the Authoring Layer; they should not be written back directly into the source data unless an explicit Export/round-trip tool exists for doing so.

---

# Chapter 8  Separating Definitional Data from Execution State

## 8.1 World Prototypes

```csv
character_id,name,default_location,base_level
npc_guard_001,沉默守衛,room_south_gate,3
```

This is a character definition.

## 8.2 Runtime State

```json
{
  "instance_id": "npc_guard_001@world_instance_42",
  "current_location": "room_market",
  "current_health": 72,
  "quest_flags": [
    "warned_player"
  ],
  "alive": true
}
```

This is world-instance state.

## 8.3 The Two Must Not Be Conflated

$$
E_{\mathrm{prototype}}
\neq
E_{\mathrm{instance}}
$$

Prototypes can be recompiled; instances record history.

If an NPC's base level is changed, it cannot be automatically assumed that every existing NPC instance should update in lockstep.

A migration policy is therefore required:

```text
Apply to new instances only
Apply to all instances
Apply only when not player-modified
Require migration script
```

---

# Chapter 9  IDs, Namespaces, and References

## 9.1 Every Entity Must Have a Stable ID

Using a display name alone as a reference is prohibited.

Incorrect:

```text
North Gate Guard
```

Correct:

```text
npc_gray_crown_gate_guard_001
```

Names can change; IDs should not be changed casually.

## 9.2 Namespace

Large worlds should support namespaces:

```text
bt:npc:guard:001
bt:item:key:old_vault
core:skill:sword_basic
mod_weather:event:black_rain
```

Formally:

$$
\mathrm{ID}
=
N
:
T
:
K
$$

Where:

- $N$: Namespace;
- $T$: Entity Type;
- $K$: Local Key.

## 9.3 Reference Resolution

The compiler needs to build:

```text
Symbol Table
Reference Graph
Dependency Graph
Reverse Reference Index
```

so that it can answer questions such as:

- Which quests would be affected by deleting an item?
- Which exits would be affected by renaming a room?
- Which skills would be affected by modifying a rule?
- Is a given NPC still referenced anywhere?

---

# Chapter 10  The AI Maintenance Workflow

## 10.1 AI Does Not Modify the Runtime Directly

AI should modify the Authoring Layer first:

```text
User Request
→ AI Patch Proposal
→ JSON／CSV Diff
→ Validation
→ Human Review
→ Compile
→ Staging
→ Runtime
```

## 10.2 AI Batch Operations

CSV is especially well suited to:

- Batch-generating 500 ordinary NPCs;
- Adjusting the damage of every low-tier skill;
- Adding translations for items;
- Checking for duplicate names;
- Updating economic prices;
- Generating test data.

JSON is well suited to:

- Generating quests;
- Adding factions;
- Establishing world axioms;
- Building complex events;
- Building rule sets.

## 10.3 AI Changes Must Be Emitted as a Diff

```yaml
patch_id: patch_0017
source_files:
  - data/items.csv
  - quests/main_quests.json

operations:
  - modify:
      file: data/items.csv
      row_id: item_old_vault_key
      field: rarity
      from: rare
      to: uncommon

  - modify:
      file: quests/main_quests.json
      path: /quests/0/rewards/0/count
      from: 1
      to: 2

validation:
  required:
    - schema
    - reference
    - quest_dependency
```

---

# Chapter 11  Versioning and Migration

## 11.1 Versions Are Divided into at Least

```text
Authoring Schema Version
World Content Version
World IR Version
Compiler Version
Runtime Adapter Version
Save Version
```

## 11.2 Authoring Layer Migration

For example:

```text
characters.csv v0.1
→ characters.csv v0.2
```

If a new field such as `memory_policy` is added, the following should be provided:

- A default value;
- A migration tool;
- Support for reading the old format;
- Warnings;
- A deprecation deadline.

## 11.3 Compilation Reproducibility

The same source, the same compiler, and the same configuration should produce the same result:

$$
C(A,v,s)
=
W
$$

This should be achieved through:

- File hashes;
- Compiler version;
- Fixed ordering;
- A fixed random seed;
- A Build Manifest;
- A Content Digest.

---

# Chapter 12  Recommended Directory Layout

```text
worlds/
└── black-tide/
    ├── manifest.json
    ├── world.json
    │
    ├── axioms/
    │   └── core.json
    │
    ├── data/
    │   ├── characters.csv
    │   ├── items.csv
    │   ├── skills.csv
    │   ├── factions.csv
    │   └── recipes.csv
    │
    ├── maps/
    │   ├── regions.json
    │   ├── rooms.csv
    │   └── exits.csv
    │
    ├── quests/
    │   ├── main_quests.json
    │   └── side_quests.json
    │
    ├── rules/
    │   ├── combat.json
    │   ├── economy.json
    │   └── magic.json
    │
    ├── events/
    │   └── world_events.json
    │
    ├── localization/
    │   ├── zh-TW.csv
    │   └── en-US.csv
    │
    ├── schemas/
    │   ├── world.schema.json
    │   ├── characters.schema.yaml
    │   └── rooms.schema.yaml
    │
    ├── patches/
    ├── migrations/
    ├── tests/
    └── build/
```

`build/` should be treated as disposable compiled output — it should never become a source that is manually edited.

---

# Chapter 13  Relationship to EML

## 13.1 JSON/CSV Will Not Be Made Obsolete by EML

EML is well suited to:

- Expressing semantics;
- Compressing rules;
- Expressing conditions;
- Expressing lifecycles;
- Expressing patches;
- Expressing dependencies;
- Serving as an interface between AI and the compiler.

JSON/CSV is well suited to:

- Large volumes of data;
- Tooling compatibility;
- Spreadsheets;
- Git;
- The existing ecosystem;
- Fast initial delivery.

The mature architecture is therefore:

$$
\mathrm{JSON/CSV}
\cup
\mathrm{EML}
\rightarrow
W_{\mathrm{IR}}
$$

rather than:

$$
\mathrm{EML}
\rightarrow
\text{eliminates JSON/CSV}
$$

## 13.2 EML Can Serve as a Semantic Overlay Layer

```eml
bind table "data/characters.csv" as characters

for character in characters {
    require character.level >= 1
    tag character.unique ? persistent : regenerable
}
```

EML does not need to duplicate and store all character data; instead, it can layer high-level semantics on top of the CSV.

---

# Chapter 14  Version 1 Development Roadmap

## Phase 0: Format Freeze

- Define `manifest.json`;
- Define IDs;
- Define namespaces;
- Define the division of labor between JSON and CSV;
- Define a minimal Schema.

## Phase 1: Loading and Normalization

- JSON Loader;
- CSV Loader;
- Encoding;
- Type conversion;
- Reference resolution;
- Error reporting.

## Phase 2: World IR

- Unified entities;
- Relationship graph;
- Rules;
- Quests;
- Maps;
- Provenance.

## Phase 3: Validation

- Schema;
- References;
- Reachability;
- Quest dependencies;
- Rule conflicts.

## Phase 4: Evennia Adapter

- Rooms;
- Exits;
- NPCs;
- Items;
- Quests;
- World version.

## Phase 5: AI Editor

- AI-generated JSON;
- AI-generated CSV;
- Diff;
- Patch;
- Review;
- Rollback.

## Phase 6: EML Semantic Layer

- Rules;
- Lifecycles;
- Persistence;
- Conditions;
- Multi-engine compilation.

---

# Chapter 15  Anti-Patterns

## 15.1 Putting All Data into a Single JSON File

Result:

- The file becomes too large;
- Git conflicts;
- Difficult multi-person collaboration;
- AI edits touch too broad a scope;
- Local validation becomes difficult.

## 15.2 Putting All Data into CSV

Result:

- Nested data gets flattened into strings;
- Quests and rules become hard to read;
- Relationship structures get distorted;
- Conditions become brittle.

## 15.3 Treating the Database as the Sole Editing Source

Result:

- Git can no longer track changes properly;
- Human review becomes difficult;
- AI edits become unreadable;
- The project becomes hard to rebuild;
- Test environments become hard to reproduce.

## 15.4 Runtime Writing Back Over Source Data

If the running game writes directly back to `characters.csv` or `world.json`, this causes:

- Prototypes and instances to become mixed together;
- Player behavior to contaminate design data;
- Large volumes of meaningless changes to appear in Git;
- The world to become impossible to recompile.

## 15.5 Having No Manifest

Letting the compiler guess which files to load leads to:

- Nondeterministic load order;
- Different results across environments;
- Hidden dependencies;
- Difficulty reproducing results.

---

# Chapter 16  Theoretical Significance

## 16.1 World Data Is Not a Single Format

A world itself has multiple scales and data shapes.

Therefore:

$$
W
\neq
\text{Single File}
$$

Rather:

$$
W
=
\bigcup_i D_i
+
\bigcup_j R_j
+
\bigcup_k P_k
$$

Where:

- $D_i$: data sets;
- $R_j$: relationships and rules;
- $P_k$: source, version, and persistence metadata.

## 16.2 JSON/CSV Is a Human–AI Collaboration Interface

For humans, they are:

- Readable;
- Editable;
- Searchable;
- Diffable;
- Usable in a spreadsheet.

For AI, they are:

- Structurally explicit;
- Easy to batch-generate;
- Easy to validate;
- Easy to build patches from;
- Easy to constrain output scope for.

The Authoring Layer is therefore a shared working surface for humans and AI.

## 16.3 CompilableWorld Does Not Replace Sources — It Absorbs Them

CompilableWorld's maturity should not be marked by the removal of JSON/CSV.

True maturity looks like:

> Regardless of whether the source is JSON, CSV, EML, a novel, or an existing MudLib, it can be normalized into the same verifiable world intermediate representation.

---

# Chapter 17  Conclusion

Practice shows that before CompilableWorld is complete, JSON and CSV are necessary tools — and after CompilableWorld is complete, there remains ample reason to keep them.

The correct architecture is not:

```text
JSON/CSV
→ used temporarily
→ removed later
```

but rather:

```text
JSON／CSV／EML
→ Authoring Layer
→ Normalize
→ Validate
→ World IR
→ CompilableWorld
→ Runtime
```

Where:

- JSON is responsible for structure and nested semantics;
- CSV is responsible for large volumes of uniformly-shaped data and batch maintenance;
- Manifest is responsible for the source index, versioning, and the compilation entry point;
- Schema is responsible for type and structural contracts;
- World IR is responsible for cross-format normalization;
- CompilableWorld is responsible for compiling the world after validation;
- The Database is responsible for runtime state;
- The Runtime is responsible for actual gameplay operation.

The most important principle is:

> Humans and AI edit the source data; the compiler builds the world; the Runtime executes the world; the database preserves the history of world instances.

Only when the boundaries among these four are kept clear can CompilableWorld remain, all at once:

- Readable;
- Maintainable;
- Verifiable;
- Portable;
- Versionable;
- Cross-engine;
- Continuously extensible by AI.

---

# Appendix A  Minimal Manifest Example

```json
{
  "world_id": "demo_world",
  "world_version": "0.1.0",
  "schema_version": "0.1.0",
  "namespace": "demo",
  "compiler_version": "0.1.0",
  "targets": [
    "evennia"
  ],
  "sources": {
    "world": "world.json",
    "characters": [
      "data/characters.csv"
    ],
    "items": [
      "data/items.csv"
    ],
    "rooms": [
      "maps/rooms.csv"
    ],
    "exits": [
      "maps/exits.csv"
    ],
    "quests": [
      "quests/quests.json"
    ]
  }
}
```

---

# Appendix B  Version 1 Validation Checklist

- [ ] All JSON parses correctly
- [ ] All CSV uses UTF-8
- [ ] All table columns conform to the Schema
- [ ] All entity IDs are unique
- [ ] All references resolve
- [ ] All room reachability has been checked
- [ ] All quest prerequisites are satisfiable
- [ ] No world axioms directly conflict
- [ ] Every file listed in the Manifest exists
- [ ] The compiler version has been recorded
- [ ] The World IR can be rebuilt
- [ ] Build output is not treated as a hand-edited source
- [ ] Runtime state is not written back to source data
- [ ] AI changes are presented as a diff/patch
- [ ] Version migrations are covered by tests

---

# Appendix C  Recommended Source Priority

When the same information appears in multiple sources:

```text
Manually approved patch
> Explicit EML rules
> JSON structural definitions
> CSV prototype data
> AI-inferred values
> Default values
```

If a conflict arises, the compiler should not silently pick a winner — it should output a conflict report.
