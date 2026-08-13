from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from compilableworld.compiler import compile_world
from compilableworld.kernel import KernelTransactionError, WorldRuntime
from compilableworld.models import ActionIR
from compilableworld.modules import install_builtin_modules
from compilableworld.player_generation import generate_character, template_catalog


ROOT = Path(__file__).resolve().parents[1]
PEACE_CITY = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class PlayerGenerationTests(unittest.TestCase):
    def test_formula_backed_template_profile(self) -> None:
        profile = generate_character(template_id="balanced", seed=7, name="測試旅者")
        self.assertEqual(profile.attributes, {"str": 13, "con": 13, "mag": 13, "agi": 13, "dex": 13})
        self.assertEqual(profile.hp_max, 104)
        self.assertEqual(profile.mp_max, 65)
        self.assertEqual(profile.fp_max, 52)
        self.assertEqual(profile.formula["attribute_floor"], 10)

    def test_package_functions_drive_generated_derived_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = json.loads(compile_world(PEACE_CITY, temp).read_text(encoding="utf-8"))
        profile = generate_character(template_id="balanced", seed=7, package=package)

        self.assertEqual(profile.formula["functions"]["attribute"], "player.attribute_from_weight")
        self.assertEqual(profile.formula["functions"]["hp"], "combat.hp_from_con")
        self.assertEqual(profile.derived, {"hp_max": 104, "mp_max": 65, "fp_max": 52})

    def test_seed_reproduces_random_template(self) -> None:
        first = generate_character(randomize=True, seed=1234)
        second = generate_character(randomize=True, seed=1234)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.mode, "random")

    def test_custom_attributes_are_overrides_not_a_second_formula(self) -> None:
        profile = generate_character(
            template_id="balanced",
            seed=7,
            attribute_overrides={"str": 20, "mag": 16},
        )
        self.assertEqual(profile.attributes["str"], 20)
        self.assertEqual(profile.attributes["mag"], 16)
        self.assertEqual(profile.attributes["con"], 13)
        self.assertEqual(profile.mode, "custom")
        self.assertEqual(profile.formula["override_attributes"], {"str": 20, "mag": 16})

    def test_runtime_materializes_and_replaces_fixed_default_player(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(PEACE_CITY, temp)
            runtime = WorldRuntime.from_package(package_path)
            profile = generate_character(template_id="vanguard", seed=99, name="前線旅者")
            actor = runtime.create_player(profile)

            self.assertFalse(runtime.registry.contains("player.newcomer"))
            self.assertTrue(runtime.registry.contains(actor))
            self.assertEqual(runtime.state.get(actor, "position", "room"), "room.registration_office")
            self.assertEqual(runtime.state.get(actor, "health", "max"), profile.hp_max)
            self.assertEqual(runtime.state.get(actor, "magic", "mp_max"), profile.mp_max)
            self.assertEqual(runtime.state.get(actor, "quest", "quest.find_work"), "unstarted")
            self.assertEqual(runtime.registry.get(actor).metadata["generation"]["template_id"], "vanguard")

    def test_generated_player_survives_snapshot_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(PEACE_CITY, temp)
            runtime = WorldRuntime.from_package(package_path)
            actor = runtime.create_player(generate_character(seed=11, name="Snapshot旅者"))
            snapshot = Path(temp) / "generated-player.snapshot.json"
            runtime.save_snapshot(snapshot)

            restored = WorldRuntime.from_package(package_path)
            restored.load_snapshot(snapshot)
            self.assertTrue(restored.registry.contains(actor))
            self.assertFalse(restored.registry.contains("player.newcomer"))
            self.assertEqual(
                {entity.entity_id for entity in restored.registry.values()},
                {entity.entity_id for entity in runtime.registry.values()},
            )
            self.assertEqual(restored.active_player_id, actor)
            self.assertEqual(restored.state.get(actor, "position", "room"), "room.registration_office")
            self.assertEqual(restored.player_profiles[actor]["seed"], 11)

    def test_generated_player_and_gameplay_are_reconstructed_by_event_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(PEACE_CITY, temp)
            event_log = Path(temp) / "generated-events.jsonl"
            runtime = WorldRuntime.from_package(package_path, event_log)
            install_builtin_modules(runtime)
            profile = generate_character(
                template_id="vanguard", seed=813, name="Replay旅者",
                package=runtime.package,
            )
            actor = runtime.create_player(profile)
            runtime.submit(ActionIR(actor, "take", "item.provisional_id_tag"))
            runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))

            self.assertEqual(runtime.event_log.events[0].event_type, "player.materialized")
            replayed = WorldRuntime.from_package(package_path)
            replayed.replay(runtime.event_log.events)

            self.assertTrue(replayed.registry.contains(actor))
            self.assertFalse(replayed.registry.contains("player.newcomer"))
            self.assertEqual(replayed.dynamic_entities, {actor})
            self.assertEqual(replayed.active_player_id, actor)
            self.assertEqual(replayed.player_profiles[actor], profile.to_dict())
            self.assertEqual(replayed.state.export(), runtime.state.export())

            snapshot = Path(temp) / "generated-player.snapshot.json"
            runtime.save_snapshot(snapshot)
            restored = WorldRuntime.from_package(package_path)
            restored.load_snapshot(snapshot)
            self.assertEqual(
                {entity.entity_id for entity in replayed.registry.values()},
                {entity.entity_id for entity in restored.registry.values()},
            )

    def test_tampered_player_materialization_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(PEACE_CITY, temp)
            runtime = WorldRuntime.from_package(package_path)
            actor = runtime.create_player(generate_character(
                seed=19, name="完整性旅者", package=runtime.package,
            ))
            tampered = deepcopy(runtime.event_log.events)
            tampered[0].payload["profile"]["hp_max"] += 1
            replayed = WorldRuntime.from_package(package_path)

            with self.assertRaisesRegex(RuntimeError, "not reproducible"):
                replayed.replay(tampered)

            self.assertFalse(replayed.registry.contains(actor))
            self.assertEqual(replayed.dynamic_entities, set())
            self.assertIsNone(replayed.active_player_id)

    def test_player_materialization_rolls_back_when_event_log_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(PEACE_CITY, temp)
            runtime = WorldRuntime.from_package(package_path)
            before_state = runtime.state.export()
            before_entities = {entity.entity_id for entity in runtime.registry.values()}

            with patch.object(
                runtime.event_log, "append",
                side_effect=KernelTransactionError("simulated player event failure"),
            ):
                with self.assertRaises(KernelTransactionError):
                    runtime.create_player(generate_character(
                        seed=20, name="Rollback旅者", package=runtime.package,
                    ))

            self.assertEqual(runtime.state.export(), before_state)
            self.assertEqual(
                {entity.entity_id for entity in runtime.registry.values()},
                before_entities,
            )
            self.assertEqual(runtime.dynamic_entities, set())
            self.assertEqual(runtime.player_profiles, {})
            self.assertIsNone(runtime.active_player_id)

    def test_replacing_generated_player_transfers_carried_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package_path = compile_world(ROOT / "examples" / "gray_crown", temp)
            runtime = WorldRuntime.from_package(package_path)
            install_builtin_modules(runtime)
            old_actor = runtime.create_player(generate_character(seed=21, name="Old"))
            taken = runtime.submit(ActionIR(old_actor, "take", "item.old_key"))
            self.assertEqual(taken.status.value, "completed")

            new_actor = runtime.create_player(
                generate_character(seed=22, name="New"),
                replace_actor_id=old_actor,
                replace_default=False,
            )

            self.assertFalse(runtime.registry.contains(old_actor))
            self.assertTrue(runtime.registry.contains(new_actor))
            self.assertEqual(
                runtime.state.get("item.old_key", "inventory", "carrier"),
                new_actor,
            )

            replayed = WorldRuntime.from_package(package_path)
            replayed.replay(runtime.event_log.events)
            self.assertFalse(replayed.registry.contains(old_actor))
            self.assertTrue(replayed.registry.contains(new_actor))
            self.assertEqual(replayed.active_player_id, new_actor)
            self.assertEqual(
                replayed.state.get("item.old_key", "inventory", "carrier"),
                new_actor,
            )

    def test_compiled_package_exposes_templates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = json.loads(compile_world(PEACE_CITY, temp).read_text(encoding="utf-8"))
        self.assertEqual(
            [item["template_id"] for item in package["player_templates"]],
            [item["template_id"] for item in template_catalog()],
        )


if __name__ == "__main__":
    unittest.main()
