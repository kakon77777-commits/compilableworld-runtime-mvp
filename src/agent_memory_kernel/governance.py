"""Write gates for AMK v0.1.

This module intentionally contains policy checks rather than model prompts.
An agent may propose a memory; it cannot use a generated answer as a shortcut
around provenance, review separation or scope boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .contracts import (
    ActorIdentity,
    ActorRole,
    Authority,
    EvidenceStatus,
    MemoryEntry,
    MemoryScope,
    ReviewDecision,
)


class PolicyDenied(ValueError):
    pass


SENSITIVE_KEYWORDS = {
    "password",
    "passphrase",
    "secret",
    "api_key",
    "apikey",
    "token",
    "private_key",
    "privatekey",
    "otp",
    "cvv",
    "credit_card",
    "card_number",
}


def sanitize_payload(value: Any) -> tuple[Any, bool]:
    """Mask common secret-bearing fields before the Raw ledger receives them."""

    if isinstance(value, dict):
        masked = False
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SENSITIVE_KEYWORDS or any(word in normalized for word in ("password", "secret", "private_key")):
                result[str(key)] = "[REDACTED]"
                masked = True
            else:
                child, child_masked = sanitize_payload(item)
                result[str(key)] = child
                masked = masked or child_masked
        return result, masked
    if isinstance(value, list):
        result = []
        masked = False
        for item in value:
            child, child_masked = sanitize_payload(item)
            result.append(child)
            masked = masked or child_masked
        return result, masked
    if isinstance(value, tuple):
        child, masked = sanitize_payload(list(value))
        return child, masked
    return value, False


@dataclass(frozen=True, slots=True)
class ValidationReport:
    checks: dict[str, str]

    @property
    def passes(self) -> bool:
        return all(value in {"pass", "warning"} for value in self.checks.values())

    @property
    def failure_reason(self) -> str | None:
        failed = [f"{name}: {value}" for name, value in self.checks.items() if value not in {"pass", "warning"}]
        return "; ".join(failed) or None


class MemoryGovernor:
    REVIEWER_ROLES = {ActorRole.HUMAN_REVIEWER, ActorRole.DETERMINISTIC_REVIEWER, ActorRole.OPERATOR, ActorRole.SYSTEM}
    REVOCATION_ROLES = {ActorRole.HUMAN_REVIEWER, ActorRole.OPERATOR, ActorRole.SYSTEM}

    def validate_candidate(
        self, candidate: MemoryEntry, evidence: Iterable[Any], requester_scope: MemoryScope | None = None,
    ) -> ValidationReport:
        evidence_events = list(evidence)
        checks: dict[str, str] = {}

        checks["schema"] = "pass" if candidate.content.strip() else "fail: empty content"
        checks["attribution"] = "pass"
        if candidate.attribution.authority is Authority.AGENT_INFERENCE and candidate.attribution.epistemic_status is EvidenceStatus.OBS:
            checks["attribution"] = "fail: agent_inference cannot be OBS"
        if candidate.attribution.epistemic_status is EvidenceStatus.OBS and not evidence_events:
            checks["attribution"] = "fail: OBS needs direct evidence"

        checks["source_policy"] = "pass" if candidate.evidence_refs else "fail: no evidence_refs"
        if candidate.evidence_refs and len(evidence_events) != len(set(candidate.evidence_refs)):
            checks["source_policy"] = "fail: missing raw evidence"

        checks["scope_policy"] = "pass"
        for event in evidence_events:
            if not self._scope_can_flow(event.scope, candidate.scope):
                checks["scope_policy"] = "fail: evidence scope cannot flow into candidate scope"
                break
        if requester_scope is not None and not candidate.scope.permits(requester_scope):
            checks["scope_policy"] = "fail: requester cannot access candidate scope"

        checks["runtime_policy"] = "pass"
        if candidate.attribution.authority is Authority.RUNTIME_VERIFIED:
            verified = any(
                event.attribution.authority is Authority.RUNTIME_VERIFIED
                or event.actor.role is ActorRole.RUNTIME
                for event in evidence_events
            )
            if not verified:
                checks["runtime_policy"] = "fail: runtime_verified claim has no runtime evidence"

        checks["consent_policy"] = "pass"
        if candidate.scope.visibility.value == "private" and candidate.governance.consent_ref == "denied":
            checks["consent_policy"] = "fail: consent denied"
        return ValidationReport(checks)

    @staticmethod
    def _scope_can_flow(source: MemoryScope, target: MemoryScope) -> bool:
        """Allow equal-or-narrower visibility, never private-to-broader leakage."""

        if source.tenant_id != target.tenant_id:
            return False
        if source.visibility.value == "private":
            return source.owner_id == target.owner_id and target.visibility.value == "private"
        if source.visibility.value == "shared_project":
            return bool(
                source.project_id
                and source.project_id == target.project_id
                and target.visibility.value in {"private", "shared_project"}
            )
        if source.visibility.value == "world":
            return bool(
                source.world_id
                and source.world_id == target.world_id
                and target.visibility.value in {"private", "world"}
            )
        return True

    def can_review(self, reviewer: ActorIdentity, proposer: ActorIdentity) -> tuple[bool, str | None]:
        if reviewer.actor_id == proposer.actor_id:
            return False, "reviewer must be distinct from proposer"
        if reviewer.role not in self.REVIEWER_ROLES:
            return False, "reviewer role is not authorized"
        return True, None

    def can_revoke(self, actor: ActorIdentity) -> bool:
        return actor.role in self.REVOCATION_ROLES

    @staticmethod
    def decision_for(report: ValidationReport, requested_approval: bool) -> ReviewDecision:
        if not requested_approval:
            return ReviewDecision.REJECTED
        return ReviewDecision.APPROVED if report.passes else ReviewDecision.NEEDS_EVIDENCE

