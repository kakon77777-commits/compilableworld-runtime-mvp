# Static Object Re-entry v0.1

Day 3 adds a bounded, offline loop: material definitions create a tool; using
that tool changes its committed condition/history; the tool then participates
as a typed input to another generation. This proves Object Re-entry under a
fixed grammar. It does not mutate rules, types or the grammar itself.

## Authoring and loading

Add `sources.object_reentry` and `object_reentry.core` to the world's manifest.
The source uses `compilableworld.object-reentry/v0.1`, described by
`schemas/object-reentry.v0.1.schema.json`. The Compiler validates the source,
records its checksum/schema ID and produces an optional compiled grammar.
Runtime independently validates its types, bounds, references, content hash,
source-checksum binding and module binding.

Older packages keep their original fields and schema-contract map. Optional
schema discovery uses `schema_catalog(include=("object_reentry",))`.
`WorldRuntime.from_package()` chooses `EntityTransactionRuntime` when the
validated package explicitly enables this capability. A manually constructed
plain WorldRuntime cannot install the creation module.

The grammar contains up to 64 material definitions and 64 fixed recipes.
Recipes choose `none` or `tool` as their input kind and `tool` or `item` as
their output kind. A recipe allowlists materials; it cannot supply free guards,
Python code, arbitrary effects or new operators.

## Executable semantics

For a validated tool input:

```text
tool contribution = floor(tool.power * tool.condition / 100)
output power = material.power + recipe.power + tool contribution + bonus
output depth = input depth + 1 (or 1 for a bootstrap recipe)
```

The bounded bonus uses the first 64 bits of SHA-256 over
`grammar_hash|recipe_id|material_id|seed`, interpreted big-endian, modulo
`bonus_max + 1`. Its algorithm identity is `sha256-prefix64-mod/v1`.
Explicit seeds are unsigned 32-bit integers. When omitted, the seed is derived
from the Action ID and retained in the recipe. Omitting an output ID similarly
derives a stable ID for that Action; the Kernel still checks ID availability.

Both `craft` with a parent tool and `use_tool` apply the configured wear.
Tools must be carried by the actor. The actor must exist and be a character or
creature; crafting places the new item in the actor's valid room. Worn-out or
over-depth inputs are rejected. Depth is at most 8 and the demo selects 3.
This specimen uses material *definitions*, not a material-stock economy.

The module returns `StateDelta + EntityDelta + EventIR`. Parent wear and the
new object's birth share the existing atomic transaction. A failed creation
does not consume the parent tool's condition.

## Recipes, history, and restoration

Each object's metadata stores a reproducible derivation: grammar version/hash,
material/recipe, seed/bonus, depth/power, and the parent tool's ID, derivation ID,
power, condition, field versions and previous history-event reference. Current
condition and last-event reference live in owned `craft.*` State cells.
`craft.generated` and `craft.used` record the resulting historical events.

The parent record is the state read for that operation, before the operation's
own wear. Capturing that record keeps provenance compact instead of copying
the entire ancestry tree. Snapshot retains those fields, so further generation
does not require scanning an old log or retaining an earlier Runtime object.

Snapshot v0.6 and the Day 2 Entity Replay path remain in use. Replay reconstructs
committed objects; it does not rerun the generator. Hosts pin the compatible
package/module versions, and a recipe from a different grammar hash cannot
silently become an input to the current grammar. Content hashes and structural
checks are provenance/consistency evidence, not signatures of an untrusted log.

`ObjectReentryModule.visual_recipe()` returns a detached, read-only projection
of name, kind, material palette, power, condition and wear overlay. It creates
no new State or Event.

## Running and acceptance

From the repository, set `PYTHONPATH=src` and run:

```powershell
python -B examples/object_reentry_demo.py
```

The example copies the Gray Crown authoring data into a temporary workspace,
adds `examples/object_reentry_catalog.json`, then compiles normally. It compares
the same seed/material/tool before and after real wear, restores checkpoints,
replays a persistent log and continues generation. Original sources stay intact.

The normal terminal and web text parser also accepts:

```text
craft workshop.make_tool material.iron - 7 item.hammer
take item.hammer
use_tool item.hammer
craft workshop.make_blade material.iron item.hammer 23 item.blade
```

Acceptance requires a gameplay-power or legality difference, reproducible
recipes, compiler and independent Runtime rejection of invalid inputs,
transaction rollback, bounded depth/wear, read-only projection and continued
generation after Snapshot/Replay. A mutant that ignores tool condition must
fail the counterfactual witness. Current results are in the daily progress log.
