"""Watermark checkpoints and explicit local/replica acknowledgement states."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import SyncCheckpoint, new_id, sha256_json, utc_now
from .database import AMKDatabase


@dataclass(frozen=True, slots=True)
class ResumeReport:
    checkpoint: SyncCheckpoint
    compatible: bool
    raw_status: str
    clean_status: str
    index_status: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint": self.checkpoint.to_dict(),
            "compatible": self.compatible,
            "raw_status": self.raw_status,
            "clean_status": self.clean_status,
            "index_status": self.index_status,
            "warnings": list(self.warnings),
        }


class SyncCoordinator:
    """Names three different operations that are often all called 'sync'.

    `checkpoint()` proves local durable state. `acknowledge_replica()` records
    receipt by a separately trusted target. `immutable_snapshot` is an explicit
    acknowledgement state, never inferred from a send attempt.
    """

    def __init__(self, database: AMKDatabase) -> None:
        self.database = database

    def checkpoint(self, session_id: str, runtime_state: dict[str, Any]) -> SyncCheckpoint:
        checkpoint = SyncCheckpoint(
            checkpoint_id=new_id("checkpoint"),
            session_id=session_id,
            raw_sequence=self.database.raw_watermark(),
            clean_revision=self.database.clean_revision,
            index_version=self.database.index_version,
            state_hash=sha256_json(runtime_state),
            runtime_state=dict(runtime_state),
            created_at=utc_now(),
        )
        self.database.save_checkpoint(checkpoint)
        self.database.add_sync_ack(checkpoint.checkpoint_id, "local", "local_committed")
        return checkpoint

    def validate_resume(self, session_id: str, checkpoint_id: str | None = None) -> ResumeReport:
        checkpoint = self.database.get_checkpoint(checkpoint_id) if checkpoint_id else self.database.latest_checkpoint(session_id)
        if checkpoint is None:
            raise ValueError("找不到 AMK checkpoint")
        current_raw = self.database.raw_watermark()
        current_clean = self.database.clean_revision
        current_index = self.database.index_version
        raw_status = "exact" if current_raw == checkpoint.raw_sequence else "advanced" if current_raw > checkpoint.raw_sequence else "behind"
        clean_status = "exact" if current_clean == checkpoint.clean_revision else "advanced" if current_clean > checkpoint.clean_revision else "behind"
        index_status = "exact" if current_index == checkpoint.index_version else "rebuilt_or_advanced" if current_index > checkpoint.index_version else "behind"
        warnings: list[str] = []
        if raw_status == "advanced":
            warnings.append("Raw ledger 在 checkpoint 後已有新增事件；恢復時需保留其因果順序。")
        if clean_status == "advanced":
            warnings.append("Clean store 在 checkpoint 後已有新版本；不可把舊 Context Packet 當成目前 Canon。")
        if index_status == "rebuilt_or_advanced":
            warnings.append("派生索引已變動，但 canonical Raw/Clean store 仍是恢復依據。")
        compatible = all(status != "behind" for status in (raw_status, clean_status, index_status))
        return ResumeReport(
            checkpoint=checkpoint,
            compatible=compatible,
            raw_status=raw_status,
            clean_status=clean_status,
            index_status=index_status,
            warnings=tuple(warnings),
        )

    def acknowledge_replica(
        self, checkpoint_id: str, target_id: str, immutable_snapshot: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self.database.get_checkpoint(checkpoint_id) is None:
            raise ValueError("無法確認不存在的 checkpoint")
        status = "immutable_snapshot" if immutable_snapshot else "replica_acknowledged"
        self.database.add_sync_ack(checkpoint_id, target_id, status, details)

    def status(self, checkpoint_id: str) -> dict[str, Any]:
        checkpoint = self.database.get_checkpoint(checkpoint_id)
        if checkpoint is None:
            raise ValueError("找不到 checkpoint")
        acknowledgements = self.database.sync_acks(checkpoint_id)
        states = {item["status"] for item in acknowledgements}
        return {
            "checkpoint": checkpoint.to_dict(),
            "local_committed": "local_committed" in states,
            "replica_acknowledged": "replica_acknowledged" in states,
            "immutable_snapshot": "immutable_snapshot" in states,
            "acknowledgements": acknowledgements,
        }

