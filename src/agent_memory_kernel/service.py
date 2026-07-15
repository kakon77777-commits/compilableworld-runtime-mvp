"""Public local AMK service: capture → propose → review → retrieve."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from .contracts import (
    ActorIdentity,
    ActorRole,
    AttributionEnvelope,
    Authority,
    ContextPacket,
    EvidenceStatus,
    MemoryEntry,
    MemoryGovernance,
    MemoryKind,
    MemoryRelations,
    MemoryScope,
    MemoryStatus,
    PromotionContract,
    RawEvent,
    ReviewDecision,
    RiskLevel,
    new_id,
    utc_now,
)
from .database import AMKDatabase
from .governance import MemoryGovernor, PolicyDenied, sanitize_payload
from .ledger import JsonlLedger
from .retrieval import ContextCompiler, LexicalRetriever, MemoryHit
from .sync import ResumeReport, SyncCoordinator


class AgentMemoryKernel:
    """A local, dependency-free AMK v0.1 implementation.

    The service intentionally exposes no Runtime state mutation method.  Runtime
    adapters can capture evidence and compile a Context Packet, but world state
    remains owned by the CompilableWorld kernel.
    """

    def __init__(self, database_path: str | Path, ledger_path: str | Path | None = None) -> None:
        self.database = AMKDatabase(database_path)
        default_ledger = Path(database_path).with_suffix(".raw.jsonl")
        self.ledger = JsonlLedger(ledger_path or default_ledger)
        self.repaired_records = self.database.reconcile_ledger(self.ledger.iter_records())
        self.governor = MemoryGovernor()
        self.retriever = LexicalRetriever(self.database)
        self.context_compiler = ContextCompiler(self.database, self.retriever)
        self.sync = SyncCoordinator(self.database)

    def close(self) -> None:
        self.database.close()

    def __enter__(self) -> "AgentMemoryKernel":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def capture(
        self,
        actor: ActorIdentity,
        operation: str,
        scope: MemoryScope,
        payload: dict[str, Any],
        attribution: AttributionEnvelope,
        *,
        environment: dict[str, Any] | None = None,
        causal_parents: Iterable[str] = (),
        idempotency_key: str | None = None,
    ) -> RawEvent:
        """Append a Raw event and return only after JSONL fsync + SQLite commit."""

        if payload.get("do_not_persist") is True:
            raise PolicyDenied("事件明確標記為 do_not_persist，不能寫入 Raw ledger")
        existing = self.database.raw_by_idempotency(idempotency_key)
        if existing is not None:
            return existing
        safe_payload, redacted = sanitize_payload(payload)
        event = RawEvent(
            sequence=self.database.next_raw_sequence(),
            actor=actor,
            operation=operation,
            scope=scope,
            payload=dict(safe_payload),
            attribution=attribution,
            environment=dict(environment or {}),
            policy_decision="redacted" if redacted else "allowed",
            causal_parents=tuple(causal_parents),
            idempotency_key=idempotency_key,
        )
        receipt = self.ledger.append(event)
        self.database.record_raw_event(event, receipt)
        return event

    def capture_runtime_event(
        self, scope: MemoryScope, event_type: str, payload: dict[str, Any], source_id: str = "runtime",
        environment: dict[str, Any] | None = None,
    ) -> RawEvent:
        identity = ActorIdentity(source_id, ActorRole.RUNTIME)
        envelope = AttributionEnvelope(
            actor_id=source_id,
            authority=Authority.RUNTIME_VERIFIED,
            epistemic_status=EvidenceStatus.OBS,
            message_role="tool",
            source_kind="runtime_transition",
            subject_ids=tuple(str(item) for item in payload.get("subject_ids", ())),
        )
        return self.capture(identity, f"runtime.{event_type}", scope, payload, envelope, environment=environment)

    def capture_phosphor_trace(
        self, scope: MemoryScope, trace: dict[str, Any], source_id: str = "phosphor",
    ) -> RawEvent:
        identity = ActorIdentity(source_id, ActorRole.TOOL)
        envelope = AttributionEnvelope(
            actor_id=source_id,
            authority=Authority.RUNTIME_VERIFIED,
            epistemic_status=EvidenceStatus.OBS,
            message_role="tool",
            source_kind="execution_trace",
            subject_ids=tuple(str(item) for item in trace.get("subject_ids", ())),
        )
        return self.capture(identity, "phosphor.trace", scope, trace, envelope)

    def propose(
        self,
        proposer: ActorIdentity,
        *,
        kind: MemoryKind,
        scope: MemoryScope,
        content: str,
        attribution: AttributionEnvelope,
        evidence_refs: Iterable[str],
        subject_refs: Iterable[str] = (),
        value: Any = None,
        confidence: float = 0.5,
        importance: float = 0.5,
        governance: MemoryGovernance | None = None,
        relations: MemoryRelations | None = None,
        memory_id: str | None = None,
    ) -> PromotionContract:
        """Create a candidate; this does not create a Clean memory entry."""

        candidate = MemoryEntry(
            memory_id=memory_id or new_id("mem"),
            kind=kind,
            scope=scope,
            content=content,
            attribution=attribution,
            evidence_refs=tuple(evidence_refs),
            subject_refs=tuple(subject_refs),
            value=value,
            confidence=confidence,
            importance=importance,
            governance=governance or MemoryGovernance(),
            relations=relations or MemoryRelations(),
            status=MemoryStatus.PROPOSED,
        )
        audit = self.capture(
            proposer,
            "memory.proposal",
            scope,
            {
                "candidate_memory_id": candidate.memory_id,
                "kind": candidate.kind.value,
                "evidence_refs": list(candidate.evidence_refs),
                "subject_refs": list(candidate.subject_refs),
            },
            AttributionEnvelope(
                actor_id=proposer.actor_id,
                # The audit fact is observed by AMK itself.  This does not make
                # the candidate content runtime-verified; the candidate keeps
                # its own authority and epistemic status.
                authority=Authority.RUNTIME_VERIFIED,
                epistemic_status=EvidenceStatus.OBS,
                message_role="tool",
                source_kind="memory_proposal",
                subject_ids=candidate.subject_refs,
            ),
            causal_parents=candidate.evidence_refs,
        )
        contract = PromotionContract(candidate=candidate, proposer=proposer, raw_watermark=audit.sequence)
        self.database.save_proposal(contract)
        return contract

    def review(
        self, proposal_id: str, reviewer: ActorIdentity, approve: bool = True, reason: str | None = None,
        review_mode: str | None = None,
    ) -> PromotionContract:
        contract = self.database.get_proposal(proposal_id)
        if contract is None:
            raise ValueError("找不到 memory proposal")
        if contract.decision is not ReviewDecision.PENDING:
            raise ValueError("此 proposal 已完成審查，不能重複覆寫決策")

        review_event = self.capture(
            reviewer,
            "memory.review",
            contract.candidate.scope,
            {"proposal_id": proposal_id, "requested_approval": approve, "reason": reason},
            AttributionEnvelope(
                actor_id=reviewer.actor_id,
                authority=(Authority.EXPLICIT_USER if reviewer.role in {ActorRole.HUMAN_REVIEWER, ActorRole.OPERATOR}
                           else Authority.RUNTIME_VERIFIED),
                epistemic_status=EvidenceStatus.OBS,
                message_role="tool",
                source_kind="memory_review",
                subject_ids=contract.candidate.subject_refs,
            ),
            causal_parents=contract.candidate.evidence_refs,
        )
        evidence = [self.database.get_raw_event(ref) for ref in contract.candidate.evidence_refs]
        report = self.governor.validate_candidate(contract.candidate, [event for event in evidence if event is not None])
        can_review, review_error = self.governor.can_review(reviewer, contract.proposer)
        checks = dict(report.checks)
        checks["review_separation"] = "pass" if can_review else f"fail: {review_error}"
        if not can_review:
            decision = ReviewDecision.REJECTED
            effective_reason = review_error
        else:
            decision = self.governor.decision_for(report, approve)
            effective_reason = reason or report.failure_reason

        contract.validation = checks
        contract.decision = decision
        contract.reviewer = reviewer
        contract.review_mode = review_mode or (
            "human" if reviewer.role in {ActorRole.HUMAN_REVIEWER, ActorRole.OPERATOR} else "deterministic"
        )
        contract.reason = effective_reason
        contract.reviewed_at = utc_now()
        contract.raw_watermark = review_event.sequence

        if decision is ReviewDecision.APPROVED:
            promoted = self._promote_candidate(contract.candidate)
            self.database.insert_clean_entry(promoted)
            contract.resulting_memory_id = promoted.memory_id
            contract.resulting_memory_version = promoted.version
            self.capture(
                reviewer,
                "memory.promoted",
                promoted.scope,
                {"proposal_id": proposal_id, "memory_id": promoted.memory_id, "version": promoted.version},
                AttributionEnvelope(
                    actor_id=reviewer.actor_id,
                    authority=Authority.RUNTIME_VERIFIED,
                    epistemic_status=EvidenceStatus.OBS,
                    message_role="tool",
                    source_kind="promotion_audit",
                    subject_ids=promoted.subject_refs,
                ),
                causal_parents=(*promoted.evidence_refs, review_event.event_id),
            )
        self.database.save_proposal(contract)
        return contract

    def _promote_candidate(self, candidate: MemoryEntry) -> MemoryEntry:
        conflicts = self._conflicting_current_entries(candidate)
        conflict_ids = tuple(sorted({entry.memory_id for entry in conflicts} | set(candidate.relations.contradicts)))
        relations = replace(candidate.relations, contradicts=conflict_ids)
        status = MemoryStatus.DISPUTED if conflicts else MemoryStatus.ACTIVE
        return replace(
            candidate,
            version=self.database.next_entry_version(candidate.memory_id),
            status=status,
            relations=relations,
            updated_at=utc_now(),
            content_hash="",
        )

    def _conflicting_current_entries(self, candidate: MemoryEntry) -> list[MemoryEntry]:
        if not candidate.subject_refs:
            return []
        entries = self.database.list_current_entries(
            candidate.scope, (MemoryStatus.ACTIVE, MemoryStatus.DISPUTED), limit=500
        )
        return [
            entry for entry in entries
            if entry.memory_id != candidate.memory_id
            and entry.kind is candidate.kind
            and set(entry.subject_refs) & set(candidate.subject_refs)
            and entry.content.strip() != candidate.content.strip()
        ]

    def revoke(self, memory_id: str, actor: ActorIdentity, reason: str, redact_content: bool = False) -> MemoryEntry:
        if not self.governor.can_revoke(actor):
            raise PolicyDenied("只有 human reviewer、operator 或 system 可以撤銷記憶")
        current = self.database.current_entry(memory_id)
        if current is None:
            raise ValueError("找不到要撤銷的 Clean memory")
        audit = self.capture(
            actor,
            "memory.revoked",
            current.scope,
            {"memory_id": memory_id, "reason": reason, "redact_content": redact_content},
            AttributionEnvelope(
                actor_id=actor.actor_id,
                authority=Authority.EXPLICIT_USER if actor.role is not ActorRole.SYSTEM else Authority.RUNTIME_VERIFIED,
                epistemic_status=EvidenceStatus.OBS,
                message_role="tool",
                source_kind="memory_revocation",
                subject_ids=current.subject_refs,
            ),
            causal_parents=current.evidence_refs,
        )
        relations = replace(
            current.relations,
            invalidated_by=tuple(sorted(set(current.relations.invalidated_by) | {audit.event_id})),
        )
        revoked = replace(
            current,
            version=self.database.next_entry_version(memory_id),
            status=MemoryStatus.REVOKED,
            content="[REDACTED]" if redact_content else current.content,
            value=None if redact_content else current.value,
            relations=relations,
            updated_at=utc_now(),
            content_hash="",
        )
        self.database.insert_clean_entry(revoked)
        return revoked

    def redact_raw(self, event_id: str, actor: ActorIdentity, reason: str) -> bool:
        if not self.governor.can_revoke(actor):
            raise PolicyDenied("只有 human reviewer、operator 或 system 可以標記 Raw payload 為 redacted")
        event = self.database.get_raw_event(event_id)
        if event is None:
            raise ValueError("找不到 Raw event")
        self.capture(
            actor,
            "raw.redaction",
            event.scope,
            {"event_id": event_id, "reason": reason},
            AttributionEnvelope(
                actor_id=actor.actor_id,
                authority=Authority.EXPLICIT_USER if actor.role is not ActorRole.SYSTEM else Authority.RUNTIME_VERIFIED,
                epistemic_status=EvidenceStatus.OBS,
                message_role="tool",
                source_kind="raw_redaction",
                subject_ids=event.attribution.subject_ids,
            ),
            causal_parents=(event_id,),
        )
        return self.database.redact_raw_event(event_id, actor)

    def retrieve(self, requester: MemoryScope, query: str, top_k: int = 8) -> list[MemoryHit]:
        return self.retriever.clean(requester, query, top_k=top_k)

    def context(
        self, requester: MemoryScope, intent: str, risk_level: RiskLevel = RiskLevel.L1,
        token_budget: int = 4000, top_k: int = 8, force_raw_fallback: bool = False,
    ) -> ContextPacket:
        return self.context_compiler.compile(
            requester, intent, risk_level, token_budget, top_k, force_raw_fallback
        )

    def rebuild_indices(self) -> int:
        return self.database.rebuild_derived_index()

    def checkpoint(self, session_id: str, runtime_state: dict[str, Any]):
        return self.sync.checkpoint(session_id, runtime_state)

    def validate_resume(self, session_id: str, checkpoint_id: str | None = None) -> ResumeReport:
        return self.sync.validate_resume(session_id, checkpoint_id)

    def status(self) -> dict[str, Any]:
        return {
            **self.database.stats(),
            "database": str(self.database.path),
            "ledger": self.ledger.verify(),
            "repaired_records": self.repaired_records,
        }

