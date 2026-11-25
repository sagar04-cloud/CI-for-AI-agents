"""Export .donegate/events.log as OpenTelemetry OTLP JSON traces."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from donegate import __version__
from donegate.supervisor.state import EventRecord, read_events


def _hex_id(seed: str, length: int) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:length]


def _to_unix_nano(ev: EventRecord) -> str:
    return str(int(ev.timestamp.timestamp() * 1_000_000_000))


def events_to_otlp_dict(repo_root: Path, service_name: str = "donegate") -> dict[str, Any]:
    """Convert .donegate/events.log into an OTLP/JSON ExportTraceServiceRequest payload."""
    events = read_events(repo_root)
    trace_id = _hex_id(str(repo_root.resolve()), 32)
    spans: list[dict[str, Any]] = []

    for idx, ev in enumerate(events):
        span_id = _hex_id(f"{trace_id}:{idx}:{ev.event}:{ev.task_id}", 16)
        ts_nano = _to_unix_nano(ev)
        attrs: list[dict[str, Any]] = [
            {"key": "donegate.event", "value": {"stringValue": ev.event}},
        ]
        if ev.task_id:
            attrs.append({"key": "donegate.task_id", "value": {"stringValue": ev.task_id}})
        if ev.status:
            attrs.append({"key": "donegate.status", "value": {"stringValue": ev.status}})

        status_code = 2 if ev.event in ("task_failed", "budget_overrun") else 1
        spans.append(
            {
                "traceId": trace_id,
                "spanId": span_id,
                "name": f"donegate.{ev.event}",
                "kind": 1,
                "startTimeUnixNano": ts_nano,
                "endTimeUnixNano": ts_nano,
                "attributes": attrs,
                "status": {"code": status_code},
            }
        )

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}},
                        {"key": "service.version", "value": {"stringValue": __version__}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "donegate.supervisor", "version": __version__},
                        "spans": spans,
                    }
                ],
            }
        ]
    }
