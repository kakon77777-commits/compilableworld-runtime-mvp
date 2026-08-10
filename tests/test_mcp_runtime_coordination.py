from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from compilableworld_mcp import (
    BearerPrincipalResolver,
    HMACKeyRing,
    PrincipalTokenCodec,
    RequestAuthContext,
    RequestSecurityError,
    RequestSecurityPipeline,
    RuntimeCoordinationGateway,
    RuntimeOwnershipError,
    RuntimeOwnershipLeaseStore,
    RuntimeQuorumGate,
    SessionTokenCodec,
    build_runtime_coordination_asgi_app,
)


class RuntimeCoordinationTests(unittest.TestCase):
    NOW = 1_800_000_000

    def setUp(self) -> None:
        ring = HMACKeyRing({"k1": b"s" * 32}, active_kid="k1")
        principal_codec = PrincipalTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
        )
        session_codec = SessionTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
        )
        self.principal_codec = principal_codec
        self.pipeline = RequestSecurityPipeline(
            BearerPrincipalResolver(principal_codec),
            session_codec,
        )

    def _context(self, *, user_id: str = "host-a", roles: list[str] | None = None) -> RequestAuthContext:
        token = self.principal_codec.issue(
            user_id=user_id,
            client_id="coordination-client",
            roles=roles or ["admin"],
            now=self.NOW,
            ttl_seconds=300,
            token_id=f"principal-{user_id}",
        )
        return RequestAuthContext(
            request_id="coordination-request",
            transport="http",
            client_id="coordination-client",
            authorization=f"Bearer {token}",
        )

    def test_admin_principal_can_acquire_renew_and_release_shared_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeOwnershipLeaseStore(Path(directory) / "coordination.sqlite3")
            gateway = RuntimeCoordinationGateway(store, self.pipeline, max_ttl_seconds=60)
            acquired = gateway.acquire(
                self._context(),
                "world-1",
                "runtime-1",
                ttl_seconds=10,
                now=self.NOW,
            )
            renewed = gateway.renew(
                self._context(),
                acquired["lease"],
                ttl_seconds=20,
                now=self.NOW + 1,
            )
            released = gateway.release(self._context(), renewed["lease"], now=self.NOW + 1)

        self.assertEqual(acquired["lease"]["owner_id"], "host-a")
        self.assertEqual(renewed["lease"]["expires_at"], self.NOW + 21)
        self.assertTrue(released["released"])

    def test_owner_identity_is_bound_to_principal_and_role(self) -> None:
        store = RuntimeOwnershipLeaseStore()
        gateway = RuntimeCoordinationGateway(store, self.pipeline)
        gateway.acquire(self._context(), "world-1", "runtime-1", now=self.NOW)
        with self.assertRaisesRegex(RuntimeOwnershipError, "already owned"):
            gateway.acquire(self._context(user_id="host-b"), "world-1", "runtime-1", now=self.NOW)
        with self.assertRaisesRegex(RequestSecurityError, "requires the admin role"):
            gateway.acquire(
                self._context(user_id="player-1", roles=["player"]),
                "world-2",
                "runtime-2",
                now=self.NOW,
            )

    def test_admin_principals_share_one_fenced_coordinator_leader_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeOwnershipLeaseStore(Path(directory) / "coordination.sqlite3")
            gateway = RuntimeCoordinationGateway(store, self.pipeline, max_ttl_seconds=60)
            first = gateway.acquire_leader(
                self._context(),
                ttl_seconds=10,
                now=self.NOW,
            )
            with self.assertRaisesRegex(RuntimeOwnershipError, "already owned"):
                gateway.acquire_leader(
                    self._context(user_id="host-b"),
                    ttl_seconds=10,
                    now=self.NOW,
                )
            recovered = gateway.acquire_leader(
                self._context(),
                ttl_seconds=10,
                recover=True,
                now=self.NOW + 1,
            )
            renewed = gateway.renew_leader(
                self._context(),
                recovered["lease"],
                ttl_seconds=20,
                now=self.NOW + 2,
            )
            released = gateway.release_leader(
                self._context(),
                renewed["lease"],
                now=self.NOW + 2,
            )

        self.assertEqual(first["lease"]["fencing_token"], 1)
        self.assertGreater(recovered["lease"]["fencing_token"], first["lease"]["fencing_token"])
        self.assertEqual(renewed["operation"], "leader_renew")
        self.assertTrue(released["released"])

    def test_leader_endpoints_reject_a_runtime_lease(self) -> None:
        store = RuntimeOwnershipLeaseStore()
        gateway = RuntimeCoordinationGateway(store, self.pipeline)
        runtime_lease = gateway.acquire(
            self._context(),
            "world-1",
            "runtime-1",
            now=self.NOW,
        )
        with self.assertRaisesRegex(RuntimeOwnershipError, "coordination leader lease"):
            gateway.renew_leader(self._context(), runtime_lease["lease"], now=self.NOW + 1)

    def test_configured_quorum_gate_must_reach_majority_before_leader_acquire(self) -> None:
        gate = RuntimeQuorumGate(["host-a", "host-b", "host-c"])
        gateway = RuntimeCoordinationGateway(RuntimeOwnershipLeaseStore(), self.pipeline, quorum_gate=gate)
        opened = gateway.request_leader_term(self._context(user_id="host-a"), now=self.NOW)
        term = opened["quorum"]["term"]

        with self.assertRaisesRegex(RuntimeOwnershipError, "requires 2 votes"):
            gateway.acquire_leader(self._context(user_id="host-a"), term=term, now=self.NOW)
        gateway.record_leader_vote(self._context(user_id="host-a"), term, now=self.NOW)
        gateway.record_leader_vote(
            self._context(user_id="host-b"),
            term,
            candidate_id="host-a",
            now=self.NOW + 1,
        )
        acquired = gateway.acquire_leader(self._context(user_id="host-a"), term=term, now=self.NOW + 1)

        self.assertEqual(acquired["lease"]["owner_id"], "host-a")

    def test_asgi_quorum_routes_fail_closed_until_leader_quorum(self) -> None:
        gate = RuntimeQuorumGate(["host-a", "host-b", "host-c"])
        gateway = RuntimeCoordinationGateway(RuntimeOwnershipLeaseStore(), self.pipeline, quorum_gate=gate)
        app = build_runtime_coordination_asgi_app(gateway)

        term_status, term_body = asyncio.run(
            self._call(app, "/v1/runtime-ownership/leader/term", {"now": self.NOW}, self._context())
        )
        term = json.loads(term_body)["quorum"]["term"]
        blocked_status, blocked_body = asyncio.run(
            self._call(
                app,
                "/v1/runtime-ownership/leader/acquire",
                {"term": term, "now": self.NOW},
                self._context(),
            )
        )
        vote_a_status, _ = asyncio.run(
            self._call(
                app,
                "/v1/runtime-ownership/leader/vote",
                {"term": term, "now": self.NOW},
                self._context(),
            )
        )
        vote_b_status, _ = asyncio.run(
            self._call(
                app,
                "/v1/runtime-ownership/leader/vote",
                {"term": term, "candidate_id": "host-a", "now": self.NOW + 1},
                self._context(user_id="host-b"),
            )
        )
        acquired_status, acquired_body = asyncio.run(
            self._call(
                app,
                "/v1/runtime-ownership/leader/acquire",
                {"term": term, "now": self.NOW + 1},
                self._context(),
            )
        )

        self.assertEqual(term_status, 200)
        self.assertEqual(blocked_status, 409)
        self.assertEqual(json.loads(blocked_body)["error_code"], "QUORUM_NOT_REACHED")
        self.assertEqual(vote_a_status, 200)
        self.assertEqual(vote_b_status, 200)
        self.assertEqual(acquired_status, 200)
        self.assertEqual(json.loads(acquired_body)["lease"]["owner_id"], "host-a")

    def test_asgi_control_plane_dispatches_authenticated_acquire_and_renew(self) -> None:
        store = RuntimeOwnershipLeaseStore()
        gateway = RuntimeCoordinationGateway(store, self.pipeline)
        app = build_runtime_coordination_asgi_app(gateway)
        context = self._context()

        acquired_status, acquired_body = asyncio.run(
            self._call(app, "/v1/runtime-ownership/acquire", {"world_id": "world-1", "runtime_instance_id": "runtime-1", "now": self.NOW}, context)
        )
        acquired = json.loads(acquired_body)
        renewed_status, renewed_body = asyncio.run(
            self._call(app, "/v1/runtime-ownership/renew", {"lease": acquired["lease"], "now": self.NOW + 1}, context)
        )
        leader_status, leader_body = asyncio.run(
            self._call(app, "/v1/runtime-ownership/leader/acquire", {"now": self.NOW}, context)
        )
        leader = json.loads(leader_body)
        leader_renewed_status, leader_renewed_body = asyncio.run(
            self._call(app, "/v1/runtime-ownership/leader/renew", {"lease": leader["lease"], "now": self.NOW + 1}, context)
        )

        self.assertEqual(acquired_status, 200)
        self.assertEqual(renewed_status, 200)
        self.assertEqual(json.loads(renewed_body)["operation"], "renew")
        self.assertEqual(leader_status, 200)
        self.assertEqual(leader_renewed_status, 200)
        self.assertEqual(json.loads(leader_renewed_body)["operation"], "leader_renew")

    @staticmethod
    async def _call(app, path: str, payload: dict[str, object], context: RequestAuthContext):
        sent: list[dict[str, object]] = []
        body = json.dumps(payload).encode("utf-8")
        messages = [{"type": "http.request", "body": body, "more_body": False}]

        async def receive() -> dict[str, object]:
            return messages.pop(0)

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        await app(
            {
                "type": "http",
                "method": "POST",
                "path": path,
                "state": {"compilableworld.request_auth_context": context},
            },
            receive,
            send,
        )
        return sent[0]["status"], sent[1]["body"]


if __name__ == "__main__":
    unittest.main()
