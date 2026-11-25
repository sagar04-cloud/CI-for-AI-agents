"""Supervisor engine, atomic state persistence, and JSONL event log."""

from __future__ import annotations

from donegate.supervisor.engine import CheckOutcome, Supervisor
from donegate.supervisor.state import (
    EventRecord,
    RunState,
    TaskRuntimeState,
    append_event,
    load_state,
    read_events,
    save_state,
)

__all__ = [
    "CheckOutcome",
    "EventRecord",
    "RunState",
    "Supervisor",
    "TaskRuntimeState",
    "append_event",
    "load_state",
    "read_events",
    "save_state",
]
