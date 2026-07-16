from __future__ import annotations

import tempfile
import time
import unittest
import sqlite3
from pathlib import Path

from compilableworld.compiler import compile_world
from compilableworld_mcp import (
    MigrationRegistry,
    MigrationRegistryError,
    RuntimeOwnershipError,
    RuntimeOwnershipHeartbeat,
    RuntimeOwnershipLeaseStore,
    ReadOnlyWorldService,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gray_crown"


class MigrationRegistryTests(unittest.TestCase):
    def test_migrates_through_an_explicit_deterministic_chain_without_mutating_input(self) -> None:
        registry = MigrationRegistry()
        registry.register(
            "world-package",
            "v1",
            "v2",
            lambda payload: {**payload, "version": "v2", "renamed": payload.pop("legacy")},
            name="rename-legacy-field",
        )
        registry.register(
            "world-package",
            "v2",
            "v3",
            lambda payload: {**payload, "version": "v3", "normalized": True},
            name="normalize-package",
        )
        original = {"version": "v1", "legacy": "value"}

        migrated = registry.migrate(original, kind="world-package", from_version="v1", to_version="v3")

        self.assertEqual(migrated["version"], "v3")
        self.assertEqual(migrated["renamed"], "value")
        self.assertEqual(original, {"version": "v1", "legacy": "value"})
        self.assertEqual([item["name"] for item in registry.available("world-package")], [
            "rename-legacy-field",
            "normalize-package",
        ])

    def test_missing_or_invalid_migrations_fail_closed(self) -> None:
        registry = MigrationRegistry()
        with self.assertRaisesRegex(MigrationRegistryError, "no migration path"):
            registry.migrate({}, kind="snapshot", from_version="v1", to_version="v2")
        with self.assertRaisesRegex(MigrationRegistryError, "must return an object"):
            registry.register("snapshot", "v1", "v2", lambda _: [])
            registry.migrate({}, kind="snapshot", from_version="v1", to_version="v2")
        with self.assertRaisesRegex(MigrationRegistryError, "already registered"):
            registry.register("snapshot", "v1", "v3", lambda payload: payload)
            registry.register("snapshot", "v1", "v3", lambda payload: payload)


class RuntimeOwnershipLeaseStoreTests(unittest.TestCase):
    NOW = 1_800_000_000

    def test_process_local_lease_is_exclusive_and_renewable(self) -> None:
        store = RuntimeOwnershipLeaseStore()
        lease = store.acquire("world-1", "runtime-1", "host-a", ttl_seconds=10, now=self.NOW)
        self.assertEqual(store.require(lease, now=self.NOW).status, "active")
        with self.assertRaisesRegex(RuntimeOwnershipError, "already owned") as error:
            store.acquire("world-1", "runtime-1", "host-b", ttl_seconds=10, now=self.NOW)
        self.assertTrue(error.exception.retryable)

        renewed = store.renew(lease, ttl_seconds=20, now=self.NOW + 1)
        self.assertEqual(renewed.expires_at, self.NOW + 21)
        store.release(renewed, now=self.NOW + 1)
        with self.assertRaisesRegex(RuntimeOwnershipError, "released"):
            store.require(renewed, now=self.NOW + 1)

    def test_expired_lease_can_be_reclaimed_and_wrong_owner_cannot_release(self) -> None:
        store = RuntimeOwnershipLeaseStore()
        first = store.acquire("world-1", "runtime-1", "host-a", ttl_seconds=5, now=self.NOW)
        with self.assertRaisesRegex(RuntimeOwnershipError, "does not match"):
            store.require(
                type(first)(first.world_id, first.runtime_instance_id, "host-b", first.lease_id, first.issued_at, first.expires_at),
                now=self.NOW,
            )
        with self.assertRaisesRegex(RuntimeOwnershipError, "expired"):
            store.require(first, now=self.NOW + 5)
        second = store.acquire("world-1", "runtime-1", "host-b", ttl_seconds=5, now=self.NOW + 5)
        self.assertNotEqual(first.lease_id, second.lease_id)
        with self.assertRaisesRegex(RuntimeOwnershipError, "does not match"):
            store.require(first, now=self.NOW + 5)

    def test_sqlite_store_persists_hash_only_lease_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "ownership.sqlite3"
            store = RuntimeOwnershipLeaseStore(database)
            lease = store.acquire("world-1", "runtime-1", "host-a", ttl_seconds=10, now=self.NOW)
            RuntimeOwnershipLeaseStore(database).require(lease, now=self.NOW)
            raw_database = database.read_bytes()

        self.assertEqual(lease.fencing_token, 1)
        self.assertNotIn(lease.lease_id.encode("utf-8"), raw_database)

    def test_sqlite_store_migrates_legacy_lease_table_with_a_fencing_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy-ownership.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "CREATE TABLE mcp_runtime_ownership ("
                    "world_id TEXT NOT NULL, runtime_instance_id TEXT NOT NULL, owner_id TEXT NOT NULL, "
                    "lease_id_hash TEXT NOT NULL, issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, "
                    "status TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY (world_id, runtime_instance_id))"
                )
                connection.execute(
                    "INSERT INTO mcp_runtime_ownership VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("world-1", "runtime-1", "old-host", "a" * 64, 1, 2, "expired", 0),
                )
                connection.commit()
            finally:
                connection.close()
            lease = RuntimeOwnershipLeaseStore(database).acquire(
                "world-1", "runtime-1", "new-host", ttl_seconds=10, now=self.NOW
            )

        self.assertEqual(lease.fencing_token, 1)

    def test_same_owner_can_explicitly_recover_an_unexpired_lease(self) -> None:
        store = RuntimeOwnershipLeaseStore()
        first = store.acquire("world-1", "runtime-1", "host-a", ttl_seconds=10, now=self.NOW)
        recovered = store.recover("world-1", "runtime-1", "host-a", ttl_seconds=10, now=self.NOW + 1)
        self.assertNotEqual(first.lease_id, recovered.lease_id)
        self.assertGreater(recovered.fencing_token, first.fencing_token)
        self.assertEqual(store.require(recovered, now=self.NOW + 1).owner_id, "host-a")
        with self.assertRaisesRegex(RuntimeOwnershipError, "does not match"):
            store.require(first, now=self.NOW + 1)
        stale_epoch = type(recovered)(
            recovered.world_id,
            recovered.runtime_instance_id,
            recovered.owner_id,
            recovered.lease_id,
            recovered.issued_at,
            recovered.expires_at,
            recovered.fencing_token - 1,
        )
        with self.assertRaisesRegex(RuntimeOwnershipError, "fencing token"):
            store.require(stale_epoch, now=self.NOW + 1)
        with self.assertRaisesRegex(RuntimeOwnershipError, "already owned"):
            store.recover("world-1", "runtime-1", "host-b", ttl_seconds=10, now=self.NOW + 1)

    def test_heartbeat_renews_and_gracefully_releases_a_lease(self) -> None:
        current = int(time.time())
        store = RuntimeOwnershipLeaseStore()
        lease = store.acquire("world-1", "runtime-heartbeat", "host-a", ttl_seconds=2, now=current)
        heartbeat = RuntimeOwnershipHeartbeat(store, lease, ttl_seconds=2, interval_seconds=0.02)
        renewed = heartbeat.renew_once(now=current + 1)
        self.assertEqual(renewed.expires_at, current + 3)
        heartbeat.start()
        time.sleep(0.05)
        self.assertTrue(heartbeat.running)
        heartbeat.stop(release=True)
        with self.assertRaisesRegex(RuntimeOwnershipError, "released"):
            store.require(heartbeat.lease, now=int(time.time()))


class ReadOnlyWorldServiceOwnershipTests(unittest.TestCase):
    def test_service_registers_and_renews_a_shared_runtime_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runtime-ownership.sqlite3"
            package_a = compile_world(EXAMPLE, Path(directory) / "build-a")
            store_a = RuntimeOwnershipLeaseStore(database)
            service_a = ReadOnlyWorldService(
                ownership_store=store_a,
                ownership_owner_id="host-a",
                ownership_ttl_seconds=30,
            )
            world_id = service_a.register_package(package_a, runtime_instance_id="runtime-shared")
            listing = service_a.list_worlds()["worlds"][0]
            self.assertEqual(listing["ownership"]["owner_id"], "host-a")
            renewed = service_a.renew_runtime_ownership(world_id, now=int(time.time()) + 1)
            self.assertEqual(renewed["owner_id"], "host-a")

            package_b = compile_world(EXAMPLE, Path(directory) / "build-b")
            service_b = ReadOnlyWorldService(
                ownership_store=RuntimeOwnershipLeaseStore(database),
                ownership_owner_id="host-b",
                ownership_ttl_seconds=30,
            )
            with self.assertRaisesRegex(RuntimeOwnershipError, "already owned"):
                service_b.register_package(package_b, runtime_instance_id="runtime-shared")

            package_restart = compile_world(EXAMPLE, Path(directory) / "build-restart")
            service_restart = ReadOnlyWorldService(
                ownership_store=RuntimeOwnershipLeaseStore(database),
                ownership_owner_id="host-a",
                ownership_ttl_seconds=30,
            )
            service_restart.register_package(
                package_restart,
                runtime_instance_id="runtime-shared",
                recover_ownership=True,
            )
            self.assertEqual(
                service_restart.list_worlds()["worlds"][0]["ownership"]["owner_id"],
                "host-a",
            )

    def test_service_can_run_and_stop_a_runtime_ownership_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "heartbeat.sqlite3"
            package = compile_world(EXAMPLE, Path(directory) / "build")
            service = ReadOnlyWorldService(
                ownership_store=RuntimeOwnershipLeaseStore(database),
                ownership_owner_id="host-heartbeat",
                ownership_ttl_seconds=2,
            )
            world_id = service.register_package(package, runtime_instance_id="runtime-heartbeat")
            started = service.start_runtime_ownership_heartbeat(world_id, interval_seconds=0.02)
            self.assertTrue(started["heartbeat_running"])
            time.sleep(0.05)
            stopped = service.stop_runtime_ownership_heartbeat(world_id, release=True)
            self.assertTrue(stopped["released"])
            self.assertFalse(stopped["heartbeat_running"])
            self.assertIsNone(stopped["ownership"])
            service.close()


if __name__ == "__main__":
    unittest.main()
