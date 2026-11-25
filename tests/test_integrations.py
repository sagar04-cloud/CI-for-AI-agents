"""Tests for Phase 6 agent integrations and MCP stdio server."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from donegate.integrations import SUPPORTED_INTEGRATIONS, apply_integration, handle_mcp_request


def test_all_integrations_generate_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    for name in SUPPORTED_INTEGRATIONS:
        res = apply_integration(tmp_path, name)
        assert res.tested_against
        for rel in res.files_written:
            assert (tmp_path / rel).is_file()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def test_mcp_server_roundtrip(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "a.txt").write_text("hi\n", encoding="utf-8")
    (tmp_path / "done.yaml").write_text(
        """
goal: "MCP test"
tasks:
  - id: t1
    title: "Check a.txt"
    checks:
      - type: file_exists
        path: "a.txt"
""",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")

    init_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, tmp_path)
    assert init_resp is not None and init_resp["result"]["serverInfo"]["name"] == "donegate-mcp"

    list_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, tmp_path)
    assert list_resp is not None
    tool_names = {t["name"] for t in list_resp["result"]["tools"]}
    assert tool_names == {"donegate_next", "donegate_start", "donegate_check", "donegate_status"}

    check_resp = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "donegate_check", "arguments": {"task_id": "t1"}},
        },
        tmp_path,
    )
    assert check_resp is not None
    payload = json.loads(check_resp["result"]["content"][0]["text"])
    assert payload["passed"] is True
