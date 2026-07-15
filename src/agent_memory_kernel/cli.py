"""Terminal interface for the local AMK reference implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .contracts import (
    ActorIdentity,
    ActorRole,
    AttributionEnvelope,
    Authority,
    EvidenceStatus,
    MemoryGovernance,
    MemoryKind,
    MemoryScope,
    RiskLevel,
    Visibility,
)
from .service import AgentMemoryKernel
from .governance import PolicyDenied


def _json_arg(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("必須提供合法 JSON") from exc


def _identity(args: argparse.Namespace) -> ActorIdentity:
    return ActorIdentity(args.actor, ActorRole(args.actor_role))


def _scope(args: argparse.Namespace) -> MemoryScope:
    return MemoryScope(
        tenant_id=args.tenant,
        owner_id=args.owner,
        visibility=Visibility(args.visibility),
        project_id=getattr(args, "project", None),
        world_id=getattr(args, "world", None),
    )


def _attribution(args: argparse.Namespace) -> AttributionEnvelope:
    return AttributionEnvelope(
        actor_id=args.actor,
        authority=Authority(args.authority),
        epistemic_status=EvidenceStatus(args.epistemic),
        message_role=getattr(args, "message_role", "user"),
        source_kind=getattr(args, "source_kind", "direct_input"),
        speaker_id=getattr(args, "speaker", None),
        author_id=getattr(args, "author", None),
        subject_ids=tuple(getattr(args, "subject", []) or ()),
    )


def _print(value: Any) -> None:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _add_store_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", required=True, help="SQLite metadata database path")
    parser.add_argument("--ledger", help="optional Raw JSONL path; default is <db>.raw.jsonl")


def _add_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--visibility", choices=[item.value for item in Visibility], default=Visibility.PRIVATE.value)
    parser.add_argument("--project")
    parser.add_argument("--world")


def _add_actor_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--actor", required=True)
    parser.add_argument("--actor-role", choices=[item.value for item in ActorRole], required=True)


def _add_attribution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--authority", choices=[item.value for item in Authority], required=True)
    parser.add_argument("--epistemic", choices=[item.value for item in EvidenceStatus], required=True)
    parser.add_argument("--message-role", default="user")
    parser.add_argument("--source-kind", default="direct_input")
    parser.add_argument("--speaker")
    parser.add_argument("--author")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amk-local",
        description="AMK v0.1 local Raw/Clean memory kernel (no model or network dependency)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create or inspect a local AMK store")
    init.add_argument("db")
    init.add_argument("--ledger")

    record = commands.add_parser("record", help="durably append a Raw event")
    _add_store_arguments(record)
    _add_scope_arguments(record)
    _add_actor_arguments(record)
    _add_attribution_arguments(record)
    record.add_argument("--operation", required=True)
    record.add_argument("--payload", required=True, type=_json_arg)
    record.add_argument("--environment", default={}, type=_json_arg)
    record.add_argument("--parent", action="append", default=[])
    record.add_argument("--idempotency-key")

    propose = commands.add_parser("propose", help="create a candidate Clean memory; no promotion yet")
    _add_store_arguments(propose)
    _add_scope_arguments(propose)
    _add_actor_arguments(propose)
    _add_attribution_arguments(propose)
    propose.add_argument("--kind", choices=[item.value for item in MemoryKind], required=True)
    propose.add_argument("--content", required=True)
    propose.add_argument("--value", type=_json_arg)
    propose.add_argument("--evidence", action="append", default=[], required=True)
    propose.add_argument("--subject", action="append", default=[])
    propose.add_argument("--confidence", type=float, default=0.5)
    propose.add_argument("--importance", type=float, default=0.5)
    propose.add_argument("--risk", choices=[item.value for item in RiskLevel], default=RiskLevel.L1.value)
    propose.add_argument("--memory-id")

    review = commands.add_parser("review", help="approve or reject a candidate with separated reviewer identity")
    _add_store_arguments(review)
    _add_actor_arguments(review)
    review.add_argument("proposal_id")
    review.add_argument("--reject", action="store_true")
    review.add_argument("--reason")
    review.add_argument("--mode", choices=["human", "deterministic", "delegated_reviewer"])

    context = commands.add_parser("context", help="compile an attributed Clean-first Context Packet")
    _add_store_arguments(context)
    _add_scope_arguments(context)
    context.add_argument("--intent", required=True)
    context.add_argument("--risk", choices=[item.value for item in RiskLevel], default=RiskLevel.L1.value)
    context.add_argument("--budget", type=int, default=4000)
    context.add_argument("--top-k", type=int, default=8)
    context.add_argument("--raw", action="store_true", help="force Raw fallback even if Clean coverage is sufficient")

    checkpoint = commands.add_parser("checkpoint", help="create a local watermark checkpoint")
    _add_store_arguments(checkpoint)
    checkpoint.add_argument("--session", required=True)
    checkpoint.add_argument("--state", required=True, type=_json_arg)

    resume = commands.add_parser("resume-check", help="validate Raw/Clean/index watermarks before resume")
    _add_store_arguments(resume)
    resume.add_argument("--session", required=True)
    resume.add_argument("--checkpoint")

    ack = commands.add_parser("ack", help="record a replica or immutable snapshot acknowledgement")
    _add_store_arguments(ack)
    ack.add_argument("checkpoint_id")
    ack.add_argument("--target", required=True)
    ack.add_argument("--immutable", action="store_true")
    ack.add_argument("--details", default={}, type=_json_arg)

    sync_status = commands.add_parser("sync-status", help="show explicit local/replica/immutable states")
    _add_store_arguments(sync_status)
    sync_status.add_argument("checkpoint_id")

    rebuild = commands.add_parser("rebuild-index", help="rebuild disposable lexical index from canonical Clean entries")
    _add_store_arguments(rebuild)

    status = commands.add_parser("status", help="show store, ledger and watermark status")
    _add_store_arguments(status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            with AgentMemoryKernel(args.db, args.ledger) as amk:
                _print(amk.status())
            return 0
        with AgentMemoryKernel(args.db, args.ledger) as amk:
            if args.command == "record":
                event = amk.capture(
                    _identity(args), args.operation, _scope(args), args.payload, _attribution(args),
                    environment=args.environment, causal_parents=args.parent, idempotency_key=args.idempotency_key,
                )
                _print(event)
            elif args.command == "propose":
                contract = amk.propose(
                    _identity(args),
                    kind=MemoryKind(args.kind),
                    scope=_scope(args),
                    content=args.content,
                    value=args.value,
                    attribution=_attribution(args),
                    evidence_refs=args.evidence,
                    subject_refs=args.subject,
                    confidence=args.confidence,
                    importance=args.importance,
                    governance=MemoryGovernance(risk_level=RiskLevel(args.risk)),
                    memory_id=args.memory_id,
                )
                _print(contract)
            elif args.command == "review":
                _print(amk.review(args.proposal_id, _identity(args), approve=not args.reject, reason=args.reason, review_mode=args.mode))
            elif args.command == "context":
                _print(amk.context(
                    _scope(args), args.intent, RiskLevel(args.risk), args.budget, args.top_k, args.raw
                ))
            elif args.command == "checkpoint":
                _print(amk.checkpoint(args.session, args.state))
            elif args.command == "resume-check":
                _print(amk.validate_resume(args.session, args.checkpoint))
            elif args.command == "ack":
                amk.sync.acknowledge_replica(args.checkpoint_id, args.target, args.immutable, args.details)
                _print(amk.sync.status(args.checkpoint_id))
            elif args.command == "sync-status":
                _print(amk.sync.status(args.checkpoint_id))
            elif args.command == "rebuild-index":
                _print({"index_version": amk.rebuild_indices()})
            elif args.command == "status":
                _print(amk.status())
        return 0
    except (OSError, ValueError, PolicyDenied) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
