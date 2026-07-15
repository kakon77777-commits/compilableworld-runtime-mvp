from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_memory_kernel import (
    ActorIdentity,
    ActorRole,
    AgentMemoryKernel,
    AttributionEnvelope,
    Authority,
    EvidenceStatus,
    MemoryKind,
    MemoryScope,
    MemoryStatus,
    RiskLevel,
)
from agent_memory_kernel.adapters import CompilableWorldMemoryAdapter, PhosphorTraceAdapter
from agent_memory_kernel.contracts import ReviewDecision
from compilableworld.cli import _attach_optional_amk, build_parser
from compilableworld.compiler import compile_world
from compilableworld.kernel import WorldRuntime
from compilableworld.models import ActionIR, EventIR
from compilableworld.modules import install_builtin_modules


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gray_crown"
PEACE_CITY = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class FakeRuntime:
    def __init__(self) -> None:
        self.package = {"manifest": {"world_id": "test-world", "runtime_version": "0.2.0"}}


class AMKTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "amk.db"
        self.amk = AgentMemoryKernel(self.path)
        self.scope_a = MemoryScope("tenant.test", "user.a")
        self.scope_b = MemoryScope("tenant.test", "user.b")
        self.user = ActorIdentity("user.a", ActorRole.USER)
        self.agent = ActorIdentity("agent.writer", ActorRole.AGENT)
        self.reviewer = ActorIdentity("operator.memory", ActorRole.HUMAN_REVIEWER)

    def tearDown(self) -> None:
        self.amk.close()
        self.temp.cleanup()

    def _raw_user(self, text: str, scope: MemoryScope | None = None):
        target_scope = scope or self.scope_a
        return self.amk.capture(
            self.user,
            "user.input",
            target_scope,
            {"text": text},
            AttributionEnvelope(
                actor_id=self.user.actor_id,
                authority=Authority.EXPLICIT_USER,
                epistemic_status=EvidenceStatus.OBS,
                source_kind="direct_input",
            ),
        )

    def _approve(
        self, content: str, evidence_id: str, *, kind: MemoryKind = MemoryKind.SEMANTIC_CLAIM,
        scope: MemoryScope | None = None, subject: str = "project.amk",
    ):
        target_scope = scope or self.scope_a
        proposal = self.amk.propose(
            self.user,
            kind=kind,
            scope=target_scope,
            content=content,
            attribution=AttributionEnvelope(
                actor_id=self.user.actor_id,
                authority=Authority.EXPLICIT_USER,
                epistemic_status=EvidenceStatus.OBS,
                source_kind="direct_input",
            ),
            evidence_refs=[evidence_id],
            subject_refs=[subject],
        )
        result = self.amk.review(proposal.proposal_id, self.reviewer)
        self.assertEqual(result.decision, ReviewDecision.APPROVED)
        return result

    def test_raw_capture_masks_secrets_and_clean_promotion_is_auditable(self) -> None:
        raw = self.amk.capture(
            self.user,
            "user.input",
            self.scope_a,
            {"text": "記住 AMK 的本機資料庫", "api_key": "should-not-persist"},
            AttributionEnvelope(
                actor_id=self.user.actor_id,
                authority=Authority.EXPLICIT_USER,
                epistemic_status=EvidenceStatus.OBS,
            ),
        )
        self.assertEqual(raw.payload["api_key"], "[REDACTED]")
        self.assertEqual(raw.policy_decision, "redacted")
        result = self._approve("AMK v0.1 使用 SQLite 作為本機 metadata store。", raw.event_id)
        entry = self.amk.database.current_entry(result.resulting_memory_id or "")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.status, MemoryStatus.ACTIVE)
        self.assertEqual(entry.evidence_refs, (raw.event_id,))
        self.assertGreater(self.amk.database.raw_watermark(), result.raw_watermark)
        self.assertTrue(self.amk.ledger.verify()["valid"])

    def test_agent_inference_cannot_be_promoted_as_observation(self) -> None:
        raw = self.amk.capture(
            self.agent,
            "agent.reasoning",
            self.scope_a,
            {"hypothesis": "這是模型猜測"},
            AttributionEnvelope(
                actor_id=self.agent.actor_id,
                authority=Authority.AGENT_INFERENCE,
                epistemic_status=EvidenceStatus.INF,
                source_kind="agent_inference",
            ),
        )
        proposal = self.amk.propose(
            self.agent,
            kind=MemoryKind.SEMANTIC_CLAIM,
            scope=self.scope_a,
            content="未驗證的猜測被當成世界事實。",
            attribution=AttributionEnvelope(
                actor_id=self.agent.actor_id,
                authority=Authority.AGENT_INFERENCE,
                epistemic_status=EvidenceStatus.OBS,
                source_kind="agent_inference",
            ),
            evidence_refs=[raw.event_id],
            subject_refs=["claim.unverified"],
        )
        result = self.amk.review(proposal.proposal_id, self.reviewer)
        self.assertEqual(result.decision, ReviewDecision.NEEDS_EVIDENCE)
        self.assertIn("agent_inference cannot be OBS", result.validation["attribution"])
        self.assertIsNone(self.amk.database.current_entry(proposal.candidate.memory_id))

    def test_proposer_cannot_review_their_own_candidate(self) -> None:
        raw = self._raw_user("自己不能批准自己寫入的長期記憶")
        proposal = self.amk.propose(
            self.user,
            kind=MemoryKind.GOAL,
            scope=self.scope_a,
            content="建立 reviewer separation。",
            attribution=AttributionEnvelope(
                actor_id=self.user.actor_id,
                authority=Authority.EXPLICIT_USER,
                epistemic_status=EvidenceStatus.OBS,
            ),
            evidence_refs=[raw.event_id],
            subject_refs=["governance.review"],
        )
        result = self.amk.review(proposal.proposal_id, self.user)
        self.assertEqual(result.decision, ReviewDecision.REJECTED)
        self.assertIn("distinct from proposer", result.validation["review_separation"])
        self.assertIsNone(self.amk.database.current_entry(proposal.candidate.memory_id))

    def test_scope_isolation_and_conflicts_are_retained(self) -> None:
        raw_a = self._raw_user("user.a 的私有資料")
        leak = self.amk.propose(
            self.user,
            kind=MemoryKind.SEMANTIC_CLAIM,
            scope=self.scope_b,
            content="不應把 A 的資料寫入 B。",
            attribution=AttributionEnvelope(
                actor_id=self.user.actor_id,
                authority=Authority.EXPLICIT_USER,
                epistemic_status=EvidenceStatus.OBS,
            ),
            evidence_refs=[raw_a.event_id],
            subject_refs=["scope.test"],
        )
        leak_result = self.amk.review(leak.proposal_id, self.reviewer)
        self.assertEqual(leak_result.decision, ReviewDecision.NEEDS_EVIDENCE)
        self.assertIn("scope", leak_result.validation["scope_policy"])

        first = self._approve("專案資料庫選擇 SQLite。", raw_a.event_id)
        second = self._approve("專案資料庫選擇 PostgreSQL。", raw_a.event_id)
        second_entry = self.amk.database.current_entry(second.resulting_memory_id or "")
        self.assertEqual(second_entry.status, MemoryStatus.DISPUTED)
        packet = self.amk.context(self.scope_a, "project.amk 的資料庫", RiskLevel.L1)
        self.assertTrue(packet.conflicts)
        isolated = self.amk.context(self.scope_b, "project.amk 的資料庫", RiskLevel.L1)
        self.assertFalse(isolated.relevant_claims)
        self.assertIsNotNone(first.resulting_memory_id)

    def test_negative_memory_uses_raw_fallback_and_redaction_removes_context_access(self) -> None:
        failed = self.amk.capture_runtime_event(
            self.scope_a,
            "test.failed",
            {"task": "deploy", "failure_mode": "test_failed", "subject_ids": ["task.deploy"]},
        )
        result = self.amk.propose(
            self.user,
            kind=MemoryKind.NEGATIVE_MEMORY,
            scope=self.scope_a,
            content="在未通過測試時不得執行 deploy。",
            attribution=AttributionEnvelope(
                actor_id="runtime",
                authority=Authority.RUNTIME_VERIFIED,
                epistemic_status=EvidenceStatus.OBS,
                source_kind="runtime_transition",
            ),
            evidence_refs=[failed.event_id],
            subject_refs=["task.deploy"],
        )
        reviewed = self.amk.review(result.proposal_id, self.reviewer)
        self.assertEqual(reviewed.decision, ReviewDecision.APPROVED)
        packet = self.amk.context(self.scope_a, "deploy test failed", RiskLevel.L3)
        self.assertTrue(packet.raw_evidence_excerpts)
        self.assertTrue(packet.active_clean_constraints)
        self.assertIn("high_risk_task", packet.warnings)
        revoked = self.amk.revoke(reviewed.resulting_memory_id or "", self.reviewer, "使用者要求遺忘", redact_content=True)
        self.assertEqual(revoked.status, MemoryStatus.REVOKED)
        after = self.amk.context(self.scope_a, "deploy test failed", RiskLevel.L1)
        self.assertFalse(after.active_clean_constraints)
        self.assertTrue(self.amk.redact_raw(failed.event_id, self.reviewer, "測試資料清除"))
        self.assertEqual(self.amk.database.get_raw_event(failed.event_id).payload, {"redacted": True})

    def test_checkpoint_and_compilableworld_adapter_are_read_only_capture_paths(self) -> None:
        checkpoint = self.amk.checkpoint("story.session.1", {"world_id": "test-world", "tick": 4})
        report = self.amk.validate_resume("story.session.1")
        self.assertTrue(report.compatible)
        self.assertEqual(report.raw_status, "exact")
        self.amk.sync.acknowledge_replica(checkpoint.checkpoint_id, "secondary-node", immutable_snapshot=True)
        status = self.amk.sync.status(checkpoint.checkpoint_id)
        self.assertTrue(status["local_committed"])
        self.assertTrue(status["immutable_snapshot"])

        adapter = CompilableWorldMemoryAdapter(self.amk, FakeRuntime(), self.scope_a)
        adapter.on_event(EventIR(event_type="door.unlocked", source="module.door", payload={"door": "vault"}))
        trace = PhosphorTraceAdapter(self.amk, self.scope_a).capture({"trace_id": "trace.1", "step": "validated"})
        self.assertEqual(trace.operation, "phosphor.trace")
        captured = self.amk.database.raw_events(self.scope_a, limit=1)[0]
        self.assertEqual(captured.operation, "phosphor.trace")
        self.assertTrue(any(
            event.operation == "runtime.door.unlocked" for event in self.amk.database.raw_events(self.scope_a, limit=10)
        ))
        advanced = self.amk.validate_resume("story.session.1")
        self.assertEqual(advanced.raw_status, "advanced")

    def test_rebuildable_lexical_index_does_not_change_canonical_retrieval(self) -> None:
        raw = self._raw_user("AMK 需要可重建索引")
        self._approve("索引只是派生物，不能成為唯一真實來源。", raw.event_id, subject="index.policy")
        before = self.amk.retrieve(self.scope_a, "索引 真實來源")
        version_before = self.amk.database.index_version
        version_after = self.amk.rebuild_indices()
        after = self.amk.retrieve(self.scope_a, "索引 真實來源")
        self.assertGreater(version_after, version_before)
        self.assertEqual([hit.entry.memory_id for hit in before], [hit.entry.memory_id for hit in after])


class RuntimeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        package = compile_world(EXAMPLE, self.temp.name)
        self.runtime = WorldRuntime.from_package(package)
        self.scope = MemoryScope("tenant.test", "user.a", world_id="gray_crown_demo")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_bound_adapter_captures_events_without_world_write_access(self) -> None:
        amk = AgentMemoryKernel(Path(self.temp.name) / "amk.db")
        try:
            adapter = CompilableWorldMemoryAdapter(amk, self.runtime, self.scope)
            adapter.bind()
            install_builtin_modules(self.runtime)
            receipt = self.runtime.submit(ActionIR("player.neo", "take", "item.old_key"))
            self.assertEqual(receipt.status.value, "completed")
            self.assertEqual(self.runtime.state.get("item.old_key", "inventory", "carrier"), "player.neo")
            operations = [event.operation for event in amk.database.raw_events(self.scope, limit=10)]
            self.assertIn("runtime.inventory.item_added", operations)
            self.assertIn("runtime.state.committed", operations)
            self.assertEqual(adapter.status["captured"], 2)
            self.assertEqual(adapter.status["failed"], 0)
        finally:
            amk.close()

    def test_optional_adapter_failure_does_not_change_committed_runtime_outcome(self) -> None:
        class FailingAMK:
            def capture_runtime_event(self, *args, **kwargs) -> None:
                raise OSError("AMK store unavailable")

        before = self.runtime.state.export()
        adapter = CompilableWorldMemoryAdapter(FailingAMK(), self.runtime, self.scope)
        adapter.bind()
        install_builtin_modules(self.runtime)
        receipt = self.runtime.submit(ActionIR("player.neo", "look"))
        self.assertEqual(receipt.status.value, "completed")
        self.assertEqual(self.runtime.state.export(), before)
        self.assertGreater(adapter.status["failed"], 0)
        self.assertIn("AMK store unavailable", adapter.status["last_error"])

    def test_cli_exposes_opt_in_amk_storage(self) -> None:
        args = build_parser().parse_args(["play", "demo.package.json", "--amk-db", "build/amk/demo.db"])
        self.assertEqual(args.amk_db, "build/amk/demo.db")
        self.assertEqual(args.amk_tenant, "local")
        self.assertIsNone(args.amk_owner)

    def test_cli_helper_binds_raw_capture_before_module_reactions(self) -> None:
        package = compile_world(EXAMPLE, self.temp.name)
        runtime = WorldRuntime.from_package(package)
        db_path = Path(self.temp.name) / "cli-amk.db"
        args = build_parser().parse_args([
            "play", str(package), "--amk-db", str(db_path), "--amk-tenant", "tenant.cli",
        ])
        amk = _attach_optional_amk(args, runtime, "player.neo")
        self.assertIsNotNone(amk)
        try:
            install_builtin_modules(runtime)
            self.assertEqual(runtime.submit(ActionIR("player.neo", "take", "item.old_key")).status.value, "completed")
            self.assertEqual(runtime.submit(ActionIR("player.neo", "move", args={"direction": "north"})).status.value, "completed")
            self.assertEqual(runtime.submit(ActionIR("player.neo", "unlock", "door.old_vault")).status.value, "completed")
            self.assertEqual(runtime.submit(ActionIR("player.neo", "open", "door.old_vault")).status.value, "completed")
            self.assertEqual(runtime.submit(ActionIR("player.neo", "move", args={"direction": "down"})).status.value, "completed")
            scope = MemoryScope("tenant.cli", "player.neo", project_id="compilableworld-runtime", world_id="gray_crown_demo")
            operations = [event.operation for event in amk.database.raw_events(scope, limit=30, newest_first=False)]
            self.assertEqual(operations[-4:], [
                "runtime.state.committed", "runtime.movement.actor_moved",
                "runtime.state.committed", "runtime.quest.completed",
            ])
        finally:
            amk.close()

    def test_amk_captures_dialogue_then_quest_transition_in_runtime_order(self) -> None:
        package = compile_world(PEACE_CITY, self.temp.name)
        runtime = WorldRuntime.from_package(package)
        scope = MemoryScope("tenant.dialogue", "player.newcomer", world_id="mingyun_zhiyu_peace_city_slice")
        amk = AgentMemoryKernel(Path(self.temp.name) / "dialogue-amk.db")
        try:
            CompilableWorldMemoryAdapter(amk, runtime, scope).bind()
            install_builtin_modules(runtime)
            actor = "player.newcomer"
            runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))
            runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))
            receipt = runtime.submit(ActionIR(actor, "talk", "npc.foreman_laotie", args={"topic": "work"}))
            self.assertEqual(receipt.status.value, "completed")
            self.assertEqual(runtime.state.get(actor, "quest", "quest.find_work"), "available")
            operations = [event.operation for event in amk.database.raw_events(scope, limit=20, newest_first=False)]
            self.assertEqual(operations[-4:], [
                "runtime.state.committed", "runtime.dialogue.responded",
                "runtime.state.committed", "runtime.quest.transitioned",
            ])
        finally:
            amk.close()


if __name__ == "__main__":
    unittest.main()
