"""Targeted tests to ensure 85%+ coverage across core logic and CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from donegate.checks import CheckContext, get_check_registry
from donegate.cli import app
from donegate.contract import ContractValidationError, parse_contract_yaml
from donegate.contract.models import CheckSpec
from donegate.integrations import apply_integration, handle_mcp_request
from donegate.scope import match_glob
from donegate.supervisor import Supervisor

runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def test_glob_char_class_and_question() -> None:
    assert match_glob("src/a1.py", "src/a?.py")
    assert match_glob("src/b.py", "src/[ab].py")
    assert match_glob("src/c.py", "src/[!ab].py")
    assert not match_glob("src/a.py", "src/[!ab].py")


def test_checks_edge_cases(tmp_path: Path) -> None:
    reg = get_check_registry()
    ctx = CheckContext(repo_root=tmp_path)

    # Missing required fields
    assert not reg.get("command").run(CheckSpec(type="command"), ctx).passed
    assert not reg.get("test_suite").run(CheckSpec(type="test_suite"), ctx).passed
    assert not reg.get("file_exists").run(CheckSpec(type="file_exists"), ctx).passed
    assert not reg.get("file_contains").run(CheckSpec(type="file_contains"), ctx).passed
    assert not reg.get("file_contains").run(
        CheckSpec(type="file_contains", path="missing.txt", pattern="x"), ctx
    ).passed
    assert not reg.get("json_path").run(CheckSpec(type="json_path"), ctx).passed
    assert not reg.get("json_path").run(
        CheckSpec(type="json_path", path="missing.json", json_path="$.a"), ctx
    ).passed
    (tmp_path / "bad.json").write_text("{bad", encoding="utf-8")
    assert not reg.get("json_path").run(
        CheckSpec(type="json_path", path="bad.json", json_path="$.a"), ctx
    ).passed
    assert not reg.get("http_check").run(CheckSpec(type="http_check", url="ftp://x"), ctx).passed
    assert not reg.get("lint_clean").run(CheckSpec(type="lint_clean"), ctx).passed
    assert not reg.get("no_new_lint_errors").run(CheckSpec(type="no_new_lint_errors"), ctx).passed
    assert not reg.get("llm_judge").run(CheckSpec(type="llm_judge"), ctx).passed

    # Command timeout
    slow_cmd = f'"{sys.executable}" -c "import time; time.sleep(2)"'
    res_to = reg.get("command").run(
        CheckSpec(type="command", command=slow_cmd, timeout_seconds=1), ctx
    )
    assert not res_to.passed and "timed out" in res_to.message


def test_contract_yaml_errors() -> None:
    for bad in ("not: [valid", "- list_root"):
        try:
            parse_contract_yaml(bad)
            raise AssertionError("Expected ContractValidationError")
        except ContractValidationError:
            pass


def test_supervisor_skip_ask_and_cli_rich_paths(tmp_path: Path, monkeypatch: object) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "a.txt").write_text("hi\n", encoding="utf-8")
    (tmp_path / "done.yaml").write_text(
        """
version: "1"
goal: "Test strategies and CLI"
tasks:
  - id: skip-task
    title: "Skip on fail"
    priority: 90
    on_fail:
      strategy: skip_and_flag
    checks:
      - type: file_exists
        path: "never_created.txt"
  - id: ask-task
    title: "Ask human on fail"
    priority: 80
    on_fail:
      strategy: ask_human
    checks:
      - type: file_exists
        path: "also_missing.txt"
""",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")

    sup = Supervisor(tmp_path)
    sup.start("skip-task")
    assert sup.check("skip-task").status.value == "skipped"
    sup.start("ask-task")
    assert sup.check("ask-task").status.value == "awaiting_human"
    sup.approve("ask-task")

    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    assert runner.invoke(app, ["version"]).exit_code == 0
    assert runner.invoke(app, ["validate"]).exit_code == 0
    assert runner.invoke(app, ["next"]).exit_code == 0
    assert runner.invoke(app, ["status"]).exit_code == 0
    assert runner.invoke(app, ["log"]).exit_code == 0
    assert runner.invoke(app, ["doctor"]).exit_code == 0
    assert runner.invoke(app, ["report-usage", "ask-task", "--steps", "1", "--json"]).exit_code == 0
    assert runner.invoke(app, ["integrate", "claude_code"]).exit_code == 0

    # MCP unknown method & tools
    assert handle_mcp_request({"id": 1, "method": "unknown"}, tmp_path)["error"]["code"] == -32601  # type: ignore[index]
    assert handle_mcp_request({"method": "notifications/initialized"}, tmp_path) is None
    for tool, args in (
        ("donegate_next", {}),
        ("donegate_status", {}),
    ):
        resp = handle_mcp_request(
            {"id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}},
            tmp_path,
        )
        assert resp is not None and "result" in resp

    # Integrate unknown
    assert runner.invoke(app, ["integrate", "unknown_tool", "--json"]).exit_code == 1
    assert apply_integration(tmp_path, "cursor").name == "cursor"
    exported = json.loads(runner.invoke(app, ["export", "--json"]).stdout)
    assert exported["goal"] == "Test strategies and CLI"

    # CLI error branches
    assert runner.invoke(app, ["init", "--json"]).exit_code == 1  # exists without --force
    assert runner.invoke(app, ["init", "--template", "nope", "--force", "--json"]).exit_code == 1
    assert runner.invoke(app, ["start", "missing-id", "--json"]).exit_code == 1
    assert runner.invoke(app, ["check", "missing-id", "--json"]).exit_code == 1
    (tmp_path / "bad.yaml").write_text("tasks: []", encoding="utf-8")
    assert runner.invoke(app, ["validate", "--file", "bad.yaml", "--json"]).exit_code == 1
