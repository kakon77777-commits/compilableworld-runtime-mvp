"""Authenticated, actor-bound MCP action submission control plane."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from compilableworld.models import ActionIR, ActionStatus, ActionReceipt

from .action_ledger import (
    ActionReservationError,
    ActionReservationStore,
    RESERVATION_STATUS_COMPLETED,
    RESERVATION_STATUS_FAILED,
)
from .audit import build_audit_envelope
from .action_journal import ActionCommitJournalStore
from .audit_store import AuditStore, AuditStoreError
from .contracts import MCPWorldError
from .outbox import OutboxError, TransactionalOutbox
from .rate_limit import RateLimitDecision, SlidingWindowRateLimiter
from .request_security import RequestAuthContext, RequestSecurityError
from .runtime_durability import RuntimeDurabilityError, RuntimeDurabilityStore
from .secure_gateway import SECURE_READONLY_GATEWAY_CONTRACT, SecureReadOnlyMCPGateway


ACTION_RESULT_CONTRACT = "compilableworld.mcp-action-result/v0.1"


def receipt_projection(receipt: ActionReceipt) -> dict[str, Any]:
    return {
        "action_id": receipt.action_id,
        "status": receipt.status.value if isinstance(receipt.status, ActionStatus) else str(receipt.status),
        "message": receipt.message,
        "event_ids": list(receipt.event_ids),
        "changed_paths": list(receipt.changed_paths),
    }


class SecureActionMCPGateway:
    """Add the guarded write path without widening the read-only gateway."""

    def __init__(
        self,
        secure_gateway: SecureReadOnlyMCPGateway,
        *,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        reservation_store: ActionReservationStore | None = None,
        outbox: TransactionalOutbox | None = None,
        commit_journal: ActionCommitJournalStore | None = None,
        audit_store: AuditStore | None = None,
        durability_store: RuntimeDurabilityStore | None = None,
        rate_limit: int = 10,
    ) -> None:
        if int(rate_limit) <= 0:
            raise RequestSecurityError("INVALID_ACTION_POLICY", "action rate limit must be positive")
        self.secure_gateway = secure_gateway
        self.rate_limiter = rate_limiter or SlidingWindowRateLimiter(limit=rate_limit, window_seconds=60)
        self.reservation_store = reservation_store or ActionReservationStore()
        self.outbox = outbox or TransactionalOutbox()
        self.commit_journal = commit_journal or ActionCommitJournalStore()
        self.audit_store = audit_store if audit_store is not None else getattr(secure_gateway, "audit_store", None)
        self.durability_store = durability_store
        self.rate_limit = int(rate_limit)

    def submit_action(
        self,
        context: RequestAuthContext,
        action: Mapping[str, Any],
        idempotency_key: str,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.secure_gateway.pipeline.dispatch(context, now=now) as request:
            self.secure_gateway._require_live_session(request.session, now=now)
            if request.session is None:  # pragma: no cover - pipeline guarantees this
                raise RequestSecurityError("SESSION_TOKEN_MISSING", "authenticated request has no session")
            if request.session.role not in {"player", "admin"}:
                raise RequestSecurityError(
                    "PRINCIPAL_ROLE_DENIED",
                    "the current session role cannot submit actions",
                )

            normalized_action = self._normalize_action(action, request.session.actor_id)
            fingerprint = self._fingerprint(request.session, normalized_action)
            reservation = self.reservation_store.get(request.session.session_id, idempotency_key)
            if reservation is not None:
                if reservation.fingerprint != fingerprint:
                    # Reuse the store's stable conflict contract.
                    self.reservation_store.reserve(
                        request.session.session_id,
                        idempotency_key,
                        fingerprint,
                        "unused-action-id",
                        now=now,
                    )
                if reservation.status in {RESERVATION_STATUS_COMPLETED, RESERVATION_STATUS_FAILED}:
                    return self._replay(
                        reservation.result,
                        request=request,
                        idempotency_key=idempotency_key,
                        now=now,
                    )

            decision = self.rate_limiter.consume(
                f"{request.principal.user_id}:{request.session.world_id}",
                now=now,
                limit=self.rate_limit,
            )
            if not decision.allowed:
                raise RequestSecurityError(
                    "RATE_LIMITED",
                    f"action rate limit exceeded; retry after {decision.retry_after_seconds}s",
                    retryable=True,
                )

            action_ir = ActionIR(
                actor_id=request.session.actor_id,
                verb=normalized_action["verb"],
                target_id=normalized_action["target_id"],
                args=normalized_action["args"],
                authority=request.session.role,
            )
            reservation = self.reservation_store.reserve(
                request.session.session_id,
                idempotency_key,
                fingerprint,
                action_ir.action_id,
                now=now,
            )
            if reservation.status in {RESERVATION_STATUS_COMPLETED, RESERVATION_STATUS_FAILED}:
                return self._replay(
                    reservation.result,
                    request=request,
                    idempotency_key=idempotency_key,
                    now=now,
                )

            runtime = self.secure_gateway.service.runtime_for_security(request.session.session_id)
            self.commit_journal.prepare(
                request.session.session_id,
                idempotency_key,
                action_ir.action_id,
                request.session.runtime_instance_id,
                now=now,
            )
            receipt = runtime.submit(action_ir)
            runtime_durability: dict[str, Any] | None = None
            if self.durability_store is not None:
                try:
                    projection = self.durability_store.record_runtime_commit(
                        request.session.runtime_instance_id,
                        action_ir.action_id,
                        runtime.state.export(),
                        runtime.event_log.events,
                        now=now,
                    )
                    runtime_durability = {
                        "persisted": True,
                        **projection.safe_metadata(),
                    }
                except RuntimeDurabilityError as exc:
                    # The Kernel result remains authoritative. The marker makes
                    # a failed projection visible without pretending the state
                    # and the external SQLite handoff were one transaction.
                    runtime_durability = {
                        "persisted": False,
                        "error_code": exc.code,
                        "message": exc.message,
                    }
            base_result = {
                "format": ACTION_RESULT_CONTRACT,
                "read_only": False,
                "world_state_changed": receipt.status == ActionStatus.COMPLETED,
                "session_id": request.session.session_id,
                "idempotency_key": idempotency_key,
                "replayed": False,
                "receipt": receipt_projection(receipt),
                "rate_limit": decision.to_dict(),
            }
            if runtime_durability is not None:
                base_result["runtime_durability"] = runtime_durability
            base_result["audit"] = build_audit_envelope(
                request,
                "action.submit",
                outcome="completed" if receipt.status == ActionStatus.COMPLETED else "failed",
                world_state_changed=receipt.status == ActionStatus.COMPLETED,
                event_ids=receipt.event_ids,
                idempotency_key=idempotency_key,
                now=now,
            )
            outbox_error: str | None = None
            try:
                if self._shared_sqlite_handoff_available():
                    _, queued = self.commit_journal.record_runtime_and_enqueue_outbox(
                        self.outbox,
                        request.session.session_id,
                        idempotency_key,
                        action_ir.action_id,
                        request.session.runtime_instance_id,
                        base_result,
                        now=now,
                    )
                else:
                    self.commit_journal.record_runtime_committed(
                        request.session.session_id,
                        idempotency_key,
                        action_ir.action_id,
                        base_result,
                        now=now,
                    )
                    queued = self.outbox.enqueue(
                        "mcp.action.receipt",
                        request.session.session_id,
                        base_result,
                        now=now,
                        dedupe_key=f"action:{action_ir.action_id}",
                    )
                    self.commit_journal.mark_outbox_enqueued(
                        request.session.session_id,
                        idempotency_key,
                        action_ir.action_id,
                        queued.outbox_id,
                        now=now,
                    )
            except OutboxError as exc:
                if self._shared_sqlite_handoff_available():
                    self.commit_journal.record_runtime_committed(
                        request.session.session_id,
                        idempotency_key,
                        action_ir.action_id,
                        base_result,
                        now=now,
                    )
                # The Runtime result remains authoritative; the reservation
                # and durable journal make the result replayable for a later
                # delivery pass.
                outbox_error = exc.code
            final_result = {
                **base_result,
                "outbox_enqueued": outbox_error is None,
            }
            if outbox_error is not None:
                final_result["outbox_error_code"] = outbox_error
                final_result["audit"] = build_audit_envelope(
                    request,
                    "action.submit",
                    outcome="completed" if receipt.status == ActionStatus.COMPLETED else "failed",
                    world_state_changed=receipt.status == ActionStatus.COMPLETED,
                    event_ids=receipt.event_ids,
                    idempotency_key=idempotency_key,
                    delivery_pending=True,
                    now=now,
                )
            self._persist_audit(final_result, now=now)
            self.reservation_store.complete(
                request.session.session_id,
                idempotency_key,
                action_ir.action_id,
                final_result,
                succeeded=receipt.status == ActionStatus.COMPLETED,
                now=now,
            )
            return final_result

    def _persist_audit(self, payload: dict[str, Any], *, now: int | None = None) -> None:
        if self.audit_store is None:
            return
        try:
            record = self.audit_store.append(payload["audit"], now=now)
        except AuditStoreError as exc:
            payload["audit_persisted"] = False
            payload["audit_error_code"] = exc.code
            return
        payload["audit_persisted"] = True
        payload["audit_id"] = record.audit_id

    def _shared_sqlite_handoff_available(self) -> bool:
        journal_db = getattr(self.commit_journal, "db_path", None)
        outbox_db = getattr(self.outbox, "db_path", None)
        return journal_db is not None and journal_db == outbox_db

    @staticmethod
    def _normalize_action(action: Mapping[str, Any], actor_id: str) -> dict[str, Any]:
        if not isinstance(action, Mapping):
            raise MCPWorldError("INVALID_ACTION", "action must be an object")
        unknown = set(action) - {"actor_id", "verb", "target_id", "args"}
        if unknown:
            raise MCPWorldError("INVALID_ACTION", f"unsupported action fields: {sorted(unknown)}")
        supplied_actor = action.get("actor_id")
        if supplied_actor is not None and str(supplied_actor).strip() != actor_id:
            raise MCPWorldError("SESSION_SCOPE_MISMATCH", "action actor_id does not match the session actor")
        verb = str(action.get("verb", "")).strip().lower()
        if not verb or len(verb) > 80:
            raise MCPWorldError("INVALID_ACTION", "action verb must be a non-empty short string")
        target = action.get("target_id")
        if target is not None:
            target = str(target).strip() or None
        args = action.get("args", {})
        if not isinstance(args, Mapping):
            raise MCPWorldError("INVALID_ACTION", "action args must be an object")
        try:
            normalized_args = json.loads(json.dumps(dict(args), ensure_ascii=False, sort_keys=True))
        except (TypeError, ValueError) as exc:
            raise MCPWorldError("INVALID_ACTION", "action args must be JSON-compatible") from exc
        return {"actor_id": actor_id, "verb": verb, "target_id": target, "args": normalized_args}

    @staticmethod
    def _fingerprint(session: Any, action: Mapping[str, Any]) -> str:
        payload = {
            "world_id": session.world_id,
            "runtime_instance_id": session.runtime_instance_id,
            "actor_id": session.actor_id,
            "role": session.role,
            **dict(action),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _replay(
        self,
        result: dict[str, Any] | None,
        *,
        request: Any | None = None,
        idempotency_key: str | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise ActionReservationError("ACTION_RESULT_MISSING", "finalized reservation has no result")
        payload = {**deepcopy(result), "replayed": True}
        if request is not None:
            receipt = payload.get("receipt")
            event_ids = receipt.get("event_ids", []) if isinstance(receipt, Mapping) else []
            payload["audit"] = build_audit_envelope(
                request,
                "action.replay",
                outcome="replayed",
                world_state_changed=bool(payload.get("world_state_changed", False)),
                event_ids=event_ids,
                idempotency_key=idempotency_key,
                replayed=True,
                now=now,
            )
            self._persist_audit(payload, now=now)
        return payload


__all__ = [
    "ACTION_RESULT_CONTRACT",
    "SecureActionMCPGateway",
    "receipt_projection",
]
