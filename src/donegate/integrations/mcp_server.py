"""Minimal zero-dependency MCP stdio server exposing next/start/check/status."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from donegate import __version__
from donegate.contract import ContractValidationError, ScopeMode, load_contract
from donegate.supervisor import Supervisor

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "donegate_next",
        "description": "List runnable DoneGate tasks ordered by priority.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "donegate_start",
        "description": "Start a DoneGate task (snapshots git baseline and timer).",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "donegate_check",
        "description": "Run checks, scope guard, and budget checks on a task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "mode": {"type": "string", "enum": ["block", "warn", "revert-suggestion"]},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "donegate_status",
        "description": "Return current DoneGate contract run state.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "donegate_validate",
        "description": "Validate done.yaml contract schema and dependency graph.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "donegate_report",
        "description": "Return cost, token usage, retries, and scope violation summary.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def handle_mcp_request(req: dict[str, Any], repo_root: Path) -> dict[str, Any] | None:
    """Handle a single JSON-RPC 2.0 MCP request."""
    req_id: Any = req.get("id")
    method = str(req.get("method", ""))
    raw_params = req.get("params")
    params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "donegate-mcp", "version": __version__},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": _TOOLS}}

    if method == "tools/call":
        tool_name = str(params.get("name", ""))
        raw_args = params.get("arguments")
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        payload: Any
        if tool_name == "donegate_validate":
            try:
                c = load_contract(repo_root / "done.yaml")
                payload = {"valid": True, "goal": c.goal, "tasks": len(c.tasks)}
            except ContractValidationError as exc:
                payload = {"valid": False, "errors": exc.errors}
        else:
            sup = Supervisor(repo_root)
            if tool_name == "donegate_next":
                payload = [t.model_dump(mode="json") for t in sup.next_tasks()]
            elif tool_name == "donegate_start":
                rt = sup.start(str(args["task_id"]))
                payload = rt.model_dump(mode="json")
            elif tool_name == "donegate_check":
                raw_mode = args.get("mode")
                mode = ScopeMode(str(raw_mode)) if raw_mode else None
                outcome = sup.check(str(args["task_id"]), scope_mode=mode)
                payload = outcome.model_dump(mode="json")
            elif tool_name == "donegate_status":
                payload = sup.state.model_dump(mode="json")
            elif tool_name == "donegate_report":
                payload = sup.build_report()
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_mcp_stdio(repo_root: Path) -> None:
    """Run the MCP JSON-RPC 2.0 server over stdin/stdout."""
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        req: dict[str, Any] = json.loads(line)
        resp = handle_mcp_request(req, repo_root)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DoneGate MCP stdio server")
    parser.add_argument("--repo", default=".", help="Repository root path")
    ns = parser.parse_args()
    run_mcp_stdio(Path(ns.repo).resolve())
