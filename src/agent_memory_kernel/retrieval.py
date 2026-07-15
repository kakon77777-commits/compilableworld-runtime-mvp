"""Clean-first retrieval and attributed Context Packet compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import (
    Authority,
    ContextPacket,
    EvidenceStatus,
    MemoryEntry,
    MemoryKind,
    MemoryScope,
    MemoryStatus,
    RiskLevel,
    RawEvent,
)
from .database import AMKDatabase
from .text import token_coverage, tokens


@dataclass(frozen=True, slots=True)
class MemoryHit:
    entry: MemoryEntry
    score: float
    matched_tokens: int

    def to_context_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.entry.memory_id,
            "version": self.entry.version,
            "kind": self.entry.kind.value,
            "content": self.entry.content,
            "value": self.entry.value,
            "scope": self.entry.scope.to_dict(),
            "subject_refs": list(self.entry.subject_refs),
            "confidence": self.entry.confidence,
            "importance": self.entry.importance,
            "status": self.entry.status.value,
            "attribution": self.entry.attribution.to_dict(),
            "evidence_refs": list(self.entry.evidence_refs),
            "relations": self.entry.relations.to_dict(),
            "score": self.score,
            "matched_tokens": self.matched_tokens,
        }


class LexicalRetriever:
    """Dependency-free lexical retriever with canonical-store fallback."""

    def __init__(self, database: AMKDatabase) -> None:
        self.database = database

    def clean(self, requester: MemoryScope, query: str, top_k: int = 8) -> list[MemoryHit]:
        query_tokens = tokens(query)
        matches = self.database.search_current_entries(requester, query_tokens, limit=max(40, top_k * 8))
        if not matches and query_tokens:
            # The derived index is replaceable.  Scan canonical Clean entries so a
            # missing or rebuilding index never makes memory disappear.
            entries = self.database.list_current_entries(
                requester, (MemoryStatus.ACTIVE, MemoryStatus.DISPUTED), limit=500
            )
            matches = [(entry, len(query_tokens & tokens(self._entry_text(entry)))) for entry in entries]
        hits: list[MemoryHit] = []
        for rank, (entry, matched) in enumerate(matches):
            coverage = token_coverage(query_tokens, self._entry_text(entry))
            if query_tokens and matched == 0:
                continue
            status_penalty = 0.08 if entry.status is MemoryStatus.DISPUTED else 0.0
            recency = 1.0 / (1.0 + rank * 0.1)
            score = max(0.0, 0.55 * coverage + 0.20 * entry.importance + 0.15 * entry.confidence + 0.10 * recency - status_penalty)
            hits.append(MemoryHit(entry=entry, score=round(score, 6), matched_tokens=matched))
        hits.sort(key=lambda item: (-item.score, item.entry.memory_id, item.entry.version))
        return hits[:max(1, top_k)]

    def raw(self, requester: MemoryScope, query: str, top_k: int = 6) -> list[RawEvent]:
        return self.database.search_raw(requester, tokens(query), limit=top_k)

    @staticmethod
    def _entry_text(entry: MemoryEntry) -> str:
        return " ".join((entry.kind.value, entry.content, " ".join(entry.subject_refs), str(entry.value or "")))


class ContextCompiler:
    """Compiles an attributed, budgeted working packet without writing Canon."""

    HIGH_RISK = {RiskLevel.L3, RiskLevel.L4}

    def __init__(self, database: AMKDatabase, retriever: LexicalRetriever | None = None) -> None:
        self.database = database
        self.retriever = retriever or LexicalRetriever(database)

    def compile(
        self,
        requester: MemoryScope,
        intent: str,
        risk_level: RiskLevel = RiskLevel.L1,
        token_budget: int = 4000,
        top_k: int = 8,
        force_raw_fallback: bool = False,
    ) -> ContextPacket:
        clean_hits = self.retriever.clean(requester, intent, top_k=top_k)
        query_tokens = tokens(intent)
        covered = set()
        for hit in clean_hits:
            covered |= query_tokens & tokens(self.retriever._entry_text(hit.entry))
        coverage = 1.0 if not query_tokens else len(covered) / len(query_tokens)
        has_dispute = any(hit.entry.status is MemoryStatus.DISPUTED for hit in clean_hits)
        reasons: list[str] = []
        if not clean_hits:
            reasons.append("no_clean_match")
        if coverage < 0.65:
            reasons.append("insufficient_clean_coverage")
        if has_dispute:
            reasons.append("disputed_clean_claim")
        if risk_level in self.HIGH_RISK:
            reasons.append("high_risk_task")
        if force_raw_fallback:
            reasons.append("caller_requested_raw")
        raw_events = self.retriever.raw(requester, intent, top_k=6) if reasons else []

        budget = max(256, int(token_budget))
        used = 0
        selected: list[MemoryHit] = []
        for hit in clean_hits:
            cost = len(hit.entry.content)
            if selected and used + cost > budget:
                break
            selected.append(hit)
            used += cost

        claims: list[dict[str, Any]] = []
        episodes: list[dict[str, Any]] = []
        constraints: list[dict[str, Any]] = []
        runtime_truth: list[dict[str, Any]] = []
        unknowns: list[dict[str, Any]] = []
        attribution: list[dict[str, Any]] = []
        for hit in selected:
            data = hit.to_context_dict()
            entry = hit.entry
            if entry.kind is MemoryKind.EPISODE:
                episodes.append(data)
            elif entry.kind in {MemoryKind.GOVERNANCE, MemoryKind.NEGATIVE_MEMORY}:
                constraints.append(data)
            else:
                claims.append(data)
            if entry.attribution.authority is Authority.RUNTIME_VERIFIED:
                runtime_truth.append(data)
            if entry.attribution.epistemic_status is EvidenceStatus.UNK or entry.status is MemoryStatus.DISPUTED:
                unknowns.append({"memory_id": entry.memory_id, "reason": entry.status.value})
            attribution.append({
                "ref": f"{entry.memory_id}@{entry.version}",
                "actor_id": entry.attribution.actor_id,
                "authority": entry.attribution.authority.value,
                "epistemic_status": entry.attribution.epistemic_status.value,
                "scope": entry.scope.to_dict(),
            })

        raw_excerpts = [self._raw_excerpt(event) for event in raw_events]
        for event in raw_events:
            attribution.append({
                "ref": event.event_id,
                "actor_id": event.attribution.actor_id,
                "authority": event.attribution.authority.value,
                "epistemic_status": event.attribution.epistemic_status.value,
                "scope": event.scope.to_dict(),
            })
        if reasons:
            unknowns.append({"reason": "raw_fallback", "triggers": reasons})

        return ContextPacket(
            task_contract={
                "intent": intent,
                "risk_level": risk_level.value,
                "token_budget": budget,
                "budget_unit": "characters_proxy",
                "scope": requester.to_dict(),
                "clean_coverage": round(coverage, 6),
            },
            runtime_truth=runtime_truth,
            active_clean_constraints=constraints,
            relevant_claims=claims,
            relevant_episodes=episodes,
            raw_evidence_excerpts=raw_excerpts,
            conflicts=self._find_conflicts(requester, selected),
            unknowns=unknowns,
            attribution_ledger=attribution,
            watermarks={
                "raw_sequence": self.database.raw_watermark(),
                "clean_revision": self.database.clean_revision,
                "index_version": self.database.index_version,
            },
            warnings=reasons,
        )

    @staticmethod
    def _raw_excerpt(event: RawEvent) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "sequence": event.sequence,
            "operation": event.operation,
            "payload": event.payload,
            "attribution": event.attribution.to_dict(),
            "scope": event.scope.to_dict(),
            "policy_decision": event.policy_decision,
        }

    def _find_conflicts(self, requester: MemoryScope, hits: list[MemoryHit]) -> list[dict[str, Any]]:
        subject_ids = {subject for hit in hits for subject in hit.entry.subject_refs}
        if not subject_ids:
            return []
        entries = self.database.list_current_entries(
            requester, (MemoryStatus.ACTIVE, MemoryStatus.DISPUTED), limit=500
        )
        conflicts: list[dict[str, Any]] = []
        for subject in sorted(subject_ids):
            related = [entry for entry in entries if subject in entry.subject_refs]
            distinct = {entry.content for entry in related}
            if len(related) > 1 and len(distinct) > 1:
                conflicts.append({
                    "subject_ref": subject,
                    "memory_refs": [f"{entry.memory_id}@{entry.version}" for entry in related],
                    "reason": "multiple_current_claims",
                })
        return conflicts
