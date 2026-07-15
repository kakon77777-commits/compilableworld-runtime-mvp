"""Stable, dependency-free contracts for the local Agent Memory Kernel.

The contracts deliberately separate lifecycle tier (Hot/Warm/Cold) from the
epistemic zone (Raw/Clean).  They are shared by the local store, adapters and
future network implementations; no contract grants a caller permission to
change a world Runtime state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return f"sha256:{hashlib.sha256(stable_json(value).encode('utf-8')).hexdigest()}"


class EvidenceStatus(str, Enum):
    OBS = "OBS"
    INF = "INF"
    UNK = "UNK"


class Authority(str, Enum):
    EXPLICIT_USER = "explicit_user"
    RUNTIME_VERIFIED = "runtime_verified"
    SOURCE_CITED = "source_cited"
    AGENT_INFERENCE = "agent_inference"
    CHARACTER_TESTIMONY = "character_testimony"


class ActorRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    RUNTIME = "runtime"
    TOOL = "tool"
    SYSTEM = "system"
    HUMAN_REVIEWER = "human_reviewer"
    DETERMINISTIC_REVIEWER = "deterministic_reviewer"
    OPERATOR = "operator"


class Visibility(str, Enum):
    PRIVATE = "private"
    SHARED_PROJECT = "shared_project"
    TEAM = "team"
    WORLD = "world"


class MemoryKind(str, Enum):
    EVENT = "event"
    SOURCE = "source"
    SEMANTIC_CLAIM = "semantic_claim"
    EPISODE = "episode"
    GOAL = "goal"
    PROCEDURE = "procedure"
    PROJECT_STATE = "project_state"
    REFLEXIVE = "reflexive"
    GOVERNANCE = "governance"
    NEGATIVE_MEMORY = "negative_memory"


class MemoryStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    ARCHIVED = "archived"


class ReviewDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_EVIDENCE = "needs_evidence"


class RiskLevel(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


@dataclass(frozen=True, slots=True)
class ActorIdentity:
    actor_id: str
    role: ActorRole

    def to_dict(self) -> dict[str, str]:
        return {"actor_id": self.actor_id, "role": self.role.value}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ActorIdentity":
        return cls(actor_id=str(value["actor_id"]), role=ActorRole(str(value["role"])))


@dataclass(frozen=True, slots=True)
class MemoryScope:
    """Scope is both an ACL boundary and part of a memory's identity."""

    tenant_id: str
    owner_id: str
    visibility: Visibility = Visibility.PRIVATE
    project_id: str | None = None
    world_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
            "visibility": self.visibility.value,
            "project_id": self.project_id,
            "world_id": self.world_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MemoryScope":
        return cls(
            tenant_id=str(value["tenant_id"]),
            owner_id=str(value["owner_id"]),
            visibility=Visibility(str(value.get("visibility", Visibility.PRIVATE.value))),
            project_id=value.get("project_id"),
            world_id=value.get("world_id"),
        )

    @property
    def key(self) -> str:
        return stable_json(self.to_dict())

    def permits(self, requester: "MemoryScope") -> bool:
        if self.tenant_id != requester.tenant_id:
            return False
        if self.visibility is Visibility.PRIVATE:
            return self.owner_id == requester.owner_id
        if self.visibility is Visibility.SHARED_PROJECT:
            return bool(self.project_id and self.project_id == requester.project_id)
        if self.visibility is Visibility.WORLD:
            return bool(self.world_id and self.world_id == requester.world_id)
        return True


@dataclass(frozen=True, slots=True)
class AttributionEnvelope:
    actor_id: str
    authority: Authority
    epistemic_status: EvidenceStatus
    message_role: str = "user"
    source_kind: str = "direct_input"
    speaker_id: str | None = None
    author_id: str | None = None
    subject_ids: tuple[str, ...] = ()
    quote_path: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "authority": self.authority.value,
            "epistemic_status": self.epistemic_status.value,
            "message_role": self.message_role,
            "source_kind": self.source_kind,
            "speaker_id": self.speaker_id,
            "author_id": self.author_id,
            "subject_ids": list(self.subject_ids),
            "quote_path": list(self.quote_path),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AttributionEnvelope":
        return cls(
            actor_id=str(value["actor_id"]),
            authority=Authority(str(value["authority"])),
            epistemic_status=EvidenceStatus(str(value["epistemic_status"])),
            message_role=str(value.get("message_role", "user")),
            source_kind=str(value.get("source_kind", "direct_input")),
            speaker_id=value.get("speaker_id"),
            author_id=value.get("author_id"),
            subject_ids=tuple(str(item) for item in value.get("subject_ids", ())),
            quote_path=tuple(str(item) for item in value.get("quote_path", ())),
        )


@dataclass(frozen=True, slots=True)
class MemoryGovernance:
    retention_policy: str = "project_default"
    write_policy: str = "reviewer_required"
    risk_level: RiskLevel = RiskLevel.L1
    consent_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "retention_policy": self.retention_policy,
            "write_policy": self.write_policy,
            "risk_level": self.risk_level.value,
            "consent_ref": self.consent_ref,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MemoryGovernance":
        return cls(
            retention_policy=str(value.get("retention_policy", "project_default")),
            write_policy=str(value.get("write_policy", "reviewer_required")),
            risk_level=RiskLevel(str(value.get("risk_level", RiskLevel.L1.value))),
            consent_ref=value.get("consent_ref"),
        )


@dataclass(frozen=True, slots=True)
class MemoryRelations:
    derived_from: tuple[str, ...] = ()
    supports: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    invalidated_by: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "derived_from": list(self.derived_from),
            "supports": list(self.supports),
            "contradicts": list(self.contradicts),
            "supersedes": list(self.supersedes),
            "invalidated_by": list(self.invalidated_by),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MemoryRelations":
        return cls(**{name: tuple(str(item) for item in value.get(name, ())) for name in (
            "derived_from", "supports", "contradicts", "supersedes", "invalidated_by",
        )})


@dataclass(frozen=True, slots=True)
class ValidTime:
    observed_at: str = field(default_factory=utc_now)
    valid_from: str = field(default_factory=utc_now)
    valid_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"observed_at": self.observed_at, "valid_from": self.valid_from, "valid_to": self.valid_to}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ValidTime":
        return cls(
            observed_at=str(value.get("observed_at", utc_now())),
            valid_from=str(value.get("valid_from", utc_now())),
            valid_to=value.get("valid_to"),
        )


@dataclass(slots=True)
class RawEvent:
    actor: ActorIdentity
    operation: str
    scope: MemoryScope
    payload: dict[str, Any]
    attribution: AttributionEnvelope
    sequence: int = 0
    event_id: str = field(default_factory=lambda: new_id("evt"))
    timestamp: str = field(default_factory=utc_now)
    environment: dict[str, Any] = field(default_factory=dict)
    policy_decision: str = "allowed"
    causal_parents: tuple[str, ...] = ()
    idempotency_key: str | None = None

    @property
    def payload_hash(self) -> str:
        return sha256_json(self.payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "actor": self.actor.to_dict(),
            "operation": self.operation,
            "scope": self.scope.to_dict(),
            "payload": self.payload,
            "payload_hash": self.payload_hash,
            "attribution": self.attribution.to_dict(),
            "environment": self.environment,
            "policy_decision": self.policy_decision,
            "causal_parents": list(self.causal_parents),
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RawEvent":
        return cls(
            event_id=str(value["event_id"]),
            sequence=int(value["sequence"]),
            timestamp=str(value["timestamp"]),
            actor=ActorIdentity.from_dict(value["actor"]),
            operation=str(value["operation"]),
            scope=MemoryScope.from_dict(value["scope"]),
            payload=dict(value.get("payload", {})),
            attribution=AttributionEnvelope.from_dict(value["attribution"]),
            environment=dict(value.get("environment", {})),
            policy_decision=str(value.get("policy_decision", "allowed")),
            causal_parents=tuple(str(item) for item in value.get("causal_parents", ())),
            idempotency_key=value.get("idempotency_key"),
        )


@dataclass(slots=True)
class MemoryEntry:
    kind: MemoryKind
    scope: MemoryScope
    content: str
    attribution: AttributionEnvelope
    evidence_refs: tuple[str, ...]
    subject_refs: tuple[str, ...] = ()
    value: Any = None
    confidence: float = 0.5
    importance: float = 0.5
    status: MemoryStatus = MemoryStatus.PROPOSED
    valid_time: ValidTime = field(default_factory=ValidTime)
    relations: MemoryRelations = field(default_factory=MemoryRelations)
    governance: MemoryGovernance = field(default_factory=MemoryGovernance)
    memory_id: str = field(default_factory=lambda: new_id("mem"))
    version: int = 1
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    content_hash: str = ""

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(float(self.confidence), 1.0))
        self.importance = max(0.0, min(float(self.importance), 1.0))
        if not self.content_hash:
            self.content_hash = sha256_json({"content": self.content, "value": self.value})

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "version": self.version,
            "kind": self.kind.value,
            "scope": self.scope.to_dict(),
            "subject_refs": list(self.subject_refs),
            "content": {"text": self.content, "value": self.value},
            "attribution": self.attribution.to_dict(),
            "evidence_refs": list(self.evidence_refs),
            "confidence": self.confidence,
            "importance": self.importance,
            "status": self.status.value,
            "valid_time": self.valid_time.to_dict(),
            "relations": self.relations.to_dict(),
            "governance": self.governance.to_dict(),
            "integrity": {
                "content_hash": self.content_hash,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MemoryEntry":
        content = value.get("content", {})
        integrity = value.get("integrity", {})
        return cls(
            memory_id=str(value["memory_id"]),
            version=int(value.get("version", 1)),
            kind=MemoryKind(str(value["kind"])),
            scope=MemoryScope.from_dict(value["scope"]),
            subject_refs=tuple(str(item) for item in value.get("subject_refs", ())),
            content=str(content.get("text", "")),
            value=content.get("value"),
            attribution=AttributionEnvelope.from_dict(value["attribution"]),
            evidence_refs=tuple(str(item) for item in value.get("evidence_refs", ())),
            confidence=float(value.get("confidence", 0.5)),
            importance=float(value.get("importance", 0.5)),
            status=MemoryStatus(str(value.get("status", MemoryStatus.PROPOSED.value))),
            valid_time=ValidTime.from_dict(value.get("valid_time", {})),
            relations=MemoryRelations.from_dict(value.get("relations", {})),
            governance=MemoryGovernance.from_dict(value.get("governance", {})),
            created_at=str(integrity.get("created_at", utc_now())),
            updated_at=str(integrity.get("updated_at", utc_now())),
            content_hash=str(integrity.get("content_hash", "")),
        )


@dataclass(slots=True)
class PromotionContract:
    candidate: MemoryEntry
    proposer: ActorIdentity
    raw_watermark: int
    proposal_id: str = field(default_factory=lambda: new_id("proposal"))
    validation: dict[str, str] = field(default_factory=dict)
    decision: ReviewDecision = ReviewDecision.PENDING
    reviewer: ActorIdentity | None = None
    review_mode: str | None = None
    reason: str | None = None
    resulting_memory_id: str | None = None
    resulting_memory_version: int | None = None
    created_at: str = field(default_factory=utc_now)
    reviewed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "candidate_memory": self.candidate.to_dict(),
            "proposer": self.proposer.to_dict(),
            "raw_watermark": self.raw_watermark,
            "validation": self.validation,
            "review": {
                "mode": self.review_mode,
                "decision": self.decision.value,
                "reviewer": None if self.reviewer is None else self.reviewer.to_dict(),
                "reason": self.reason,
                "reviewed_at": self.reviewed_at,
            },
            "resulting_memory_version": (
                None if self.resulting_memory_id is None else f"{self.resulting_memory_id}@{self.resulting_memory_version}"
            ),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PromotionContract":
        review = value.get("review", {})
        result = value.get("resulting_memory_version")
        memory_id, version = (None, None)
        if result:
            memory_id, raw_version = str(result).rsplit("@", 1)
            version = int(raw_version)
        reviewer = review.get("reviewer")
        return cls(
            proposal_id=str(value["proposal_id"]),
            candidate=MemoryEntry.from_dict(value["candidate_memory"]),
            proposer=ActorIdentity.from_dict(value["proposer"]),
            raw_watermark=int(value["raw_watermark"]),
            validation={str(key): str(item) for key, item in value.get("validation", {}).items()},
            decision=ReviewDecision(str(review.get("decision", ReviewDecision.PENDING.value))),
            reviewer=None if reviewer is None else ActorIdentity.from_dict(reviewer),
            review_mode=review.get("mode"),
            reason=review.get("reason"),
            resulting_memory_id=memory_id,
            resulting_memory_version=version,
            created_at=str(value.get("created_at", utc_now())),
            reviewed_at=review.get("reviewed_at"),
        )


@dataclass(frozen=True, slots=True)
class SyncCheckpoint:
    checkpoint_id: str
    session_id: str
    raw_sequence: int
    clean_revision: int
    index_version: int
    state_hash: str
    runtime_state: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "raw_sequence": self.raw_sequence,
            "clean_revision": self.clean_revision,
            "index_version": self.index_version,
            "state_hash": self.state_hash,
            "runtime_state": self.runtime_state,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SyncCheckpoint":
        return cls(
            checkpoint_id=str(value["checkpoint_id"]),
            session_id=str(value["session_id"]),
            raw_sequence=int(value["raw_sequence"]),
            clean_revision=int(value["clean_revision"]),
            index_version=int(value["index_version"]),
            state_hash=str(value["state_hash"]),
            runtime_state=dict(value.get("runtime_state", {})),
            created_at=str(value["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class ContextPacket:
    task_contract: dict[str, Any]
    runtime_truth: list[dict[str, Any]]
    active_clean_constraints: list[dict[str, Any]]
    relevant_claims: list[dict[str, Any]]
    relevant_episodes: list[dict[str, Any]]
    raw_evidence_excerpts: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    unknowns: list[dict[str, Any]]
    attribution_ledger: list[dict[str, Any]]
    watermarks: dict[str, Any]
    warnings: list[str]
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_contract": self.task_contract,
            "runtime_truth": self.runtime_truth,
            "active_clean_constraints": self.active_clean_constraints,
            "relevant_claims": self.relevant_claims,
            "relevant_episodes": self.relevant_episodes,
            "raw_evidence_excerpts": self.raw_evidence_excerpts,
            "conflicts": self.conflicts,
            "unknowns": self.unknowns,
            "attribution_ledger": self.attribution_ledger,
            "watermarks": self.watermarks,
            "warnings": self.warnings,
            "created_at": self.created_at,
        }

