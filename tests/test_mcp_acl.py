from __future__ import annotations

import tempfile
import unittest

from compilableworld.compiler import compile_world
from compilableworld_mcp import MCPWorldError, ReadOnlyWorldService, WorldACL


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gray_crown"


class WorldACLTests(unittest.TestCase):
    def setUp(self) -> None:
        self.acl = WorldACL()

    def test_grant_is_role_and_actor_scoped(self) -> None:
        grant = self.acl.grant(
            "user-1",
            "world-1",
            roles=["player", "reviewer"],
            actor_ids=["player-1"],
        )
        self.assertEqual(grant.roles, ("player", "reviewer"))
        self.assertEqual(self.acl.authorize("user-1", "world-1", "player-1", "player"), grant)
        with self.assertRaisesRegex(MCPWorldError, "role"):
            self.acl.authorize("user-1", "world-1", "player-1", "admin")
        with self.assertRaisesRegex(MCPWorldError, "actor"):
            self.acl.authorize("user-1", "world-1", "npc-1", "player")

    def test_missing_and_revoked_grants_fail_closed(self) -> None:
        with self.assertRaisesRegex(MCPWorldError, "no grant"):
            self.acl.authorize("missing", "world-1", "player-1", "player")
        self.acl.grant("user-1", "world-1", roles=["player"])
        self.assertTrue(self.acl.revoke("user-1", "world-1"))
        self.assertFalse(self.acl.revoke("user-1", "world-1"))
        with self.assertRaisesRegex(MCPWorldError, "no grant"):
            self.acl.authorize("user-1", "world-1", "player-1", "player")

    def test_acl_rejects_unknown_roles_and_empty_actor_scope(self) -> None:
        with self.assertRaisesRegex(MCPWorldError, "unsupported role"):
            self.acl.grant("user-1", "world-1", roles=["root"])
        with self.assertRaisesRegex(MCPWorldError, "cannot be empty"):
            self.acl.grant("user-1", "world-1", roles=["player"], actor_ids=[])


class ServiceACLIntegrationTests(unittest.TestCase):
    def test_existing_session_is_rechecked_after_acl_revoke(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = compile_world(EXAMPLE, temp)
            acl = WorldACL()
            service = ReadOnlyWorldService(acl=acl)
            world_id = service.register_package(package, runtime_instance_id="runtime-acl")
            actor_id = service.runtime_for_testing(world_id).package["world"]["default_player_entity"]
            acl.grant("user-1", world_id, roles=["player"], actor_ids=[actor_id])
            opened = service.open_world_session(world_id, user_id="user-1")
            session_id = opened["session"]["session_id"]
            self.assertEqual(service.get_world_status(session_id)["session_id"], session_id)
            acl.revoke("user-1", world_id)
            with self.assertRaisesRegex(MCPWorldError, "no grant"):
                service.get_world_status(session_id)


if __name__ == "__main__":
    unittest.main()
