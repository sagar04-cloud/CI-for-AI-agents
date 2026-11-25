"""Atomic state.json and append-only JSONL events.log persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from donegate.contract.loader import atomic_write_text
from donegate.contract.models import TaskStatus, UsageCounters
from donegate.scope.guard import GitBaseline


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class TaskRuntimeState(BaseModel):
    """Runtime tracking state for a single task."""

    status: TaskStatus = TaskStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    baseline: GitBaseline | None = None
    usage: UsageCounters = Field(default_factory=UsageCounters)
    human_approved: bool = False
    last_summary: str = ""
    flagged_reason: str = ""


class RunState(BaseModel):
    """Persisted state of a DoneGate contract run (.donegate/state.json)."""

    contract_path: str = "done.yaml"
    goal: str = ""
    updated_at: datetime = Field(default_factory=utc_now)
    tasks: dict[str, TaskRuntimeState] = Field(default_factory=dict)


class EventRecord(BaseModel):
    """Single JSONL entry in .donegate/events.log."""

    timestamp: datetime = Field(default_factory=utc_now)
    event: str
    task_id: str | None = None
    status: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def state_dir(repo_root: Path) -> Path:
    """Return the .donegate directory inside repo_root."""
    return repo_root / ".donegate"


def load_state(repo_root: Path) -> RunState | None:
    """Load .donegate/state.json if it exists."""
    path = state_dir(repo_root) / "state.json"
    if not path.is_file():
        return None
    return RunState.model_validate_json(path.read_text(encoding="utf-8"))


def save_state(repo_root: Path, state: RunState) -> Path:
    """Atomically persist RunState to .donegate/state.json."""
    state.updated_at = utc_now()
    path = state_dir(repo_root) / "state.json"
    atomic_write_text(path, state.model_dump_json(indent=2) + "\n")
    return path


def append_event(repo_root: Path, record: EventRecord) -> Path:
    """Append an EventRecord as one JSON line to .donegate/events.log."""
    log_path = state_dir(repo_root) / "events.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.model_dump(mode="json"), separators=(",", ":")) + "\n"
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
    return log_path


def read_events(repo_root: Path) -> list[EventRecord]:
    """Read all events from .donegate/events.log."""
    log_path = state_dir(repo_root) / "events.log"
    if not log_path.is_file():
        return []
    events: list[EventRecord] = []
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            events.append(EventRecord.model_validate_json(raw))
    return events
