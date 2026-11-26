"""Tests for DoneGate v1.1 features."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from donegate import __version__
from donegate.checks import CheckContext, get_check_registry
from donegate.cli import app
from donegate.contract.models import CheckSpec
from donegate.integrations import handle_mcp_request
from donegate.ui import render_dashboard_html

runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def test_version_1_1_0() -> None:
    assert __version__ == "1.1.0"


def test_lint_baseline_json_file(tmp_path: Path) -> None:
    dg = tmp_path / ".donegate"
    dg.mkdir()
    (dg / "lint_baseline.json").write_text(json.dumps({"lint": 2}), encoding="utf-8")

    reg = get_check_registry()
    ctx = CheckContext(repo_root=tmp_path)
    two_err = f'"{sys.executable}" -c "import sys; print(\'e1\\ne2\'); sys.exit(1)"'
    three_err = f'"{sys.executable}" -c "import sys; print(\'e1\\ne2\\ne3\'); sys.exit(1)"'

    assert reg.get("no_new_lint_errors").run(
        CheckSpec(type="no_new_lint_errors", name="lint", command=two_err), ctx
    ).passed
    assert not reg.get("no_new_lint_errors").run(
        CheckSpec(type="no_new_lint_errors", name="lint", command=three_err), ctx
    ).passed


def test_check_all_reset_report_and_mcp_v1_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "a.txt").write_text("hi\n", encoding="utf-8")
    (tmp_path / "done.yaml").write_text(
        """
goal: "v1.1 test"
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

    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["start", "t1", "--json"]).exit_code == 0
    r_all = runner.invoke(app, ["check", "--all", "--json"])
    assert r_all.exit_code == 0
    assert json.loads(r_all.stdout)["passed"] is True
    assert runner.invoke(app, ["check", "--all"]).exit_code == 0  # no in_progress tasks
    assert runner.invoke(app, ["check", "--json"]).exit_code == 1  # missing task_id & --all

    r_rep = runner.invoke(app, ["report", "--json"])
    assert r_rep.exit_code == 0
    assert json.loads(r_rep.stdout)["done_tasks"] == 1
    assert runner.invoke(app, ["report"]).exit_code == 0

    r_reset = runner.invoke(app, ["reset", "t1", "--json"])
    assert r_reset.exit_code == 0
    assert json.loads(r_reset.stdout)["reset"] == ["t1"]
    assert runner.invoke(app, ["reset", "--all"]).exit_code == 0
    assert runner.invoke(app, ["reset", "--json"]).exit_code == 1
    assert runner.invoke(app, ["reset", "nope", "--json"]).exit_code == 1

    # New MCP tools + mode param
    chk_resp = handle_mcp_request(
        {
            "id": 9,
            "method": "tools/call",
            "params": {"name": "donegate_check", "arguments": {"task_id": "t1", "mode": "warn"}},
        },
        tmp_path,
    )
    assert chk_resp is not None and "result" in chk_resp

    val_resp = handle_mcp_request(
        {
            "id": 10,
            "method": "tools/call",
            "params": {"name": "donegate_validate", "arguments": {}},
        },
        tmp_path,
    )
    assert val_resp is not None
    assert json.loads(val_resp["result"]["content"][0]["text"])["valid"] is True

    rep_resp = handle_mcp_request(
        {"id": 11, "method": "tools/call", "params": {"name": "donegate_report", "arguments": {}}},
        tmp_path,
    )
    assert rep_resp is not None
    assert "total_tasks" in json.loads(rep_resp["result"]["content"][0]["text"])

    assert "setInterval" in render_dashboard_html(tmp_path)

    # Invalid done.yaml via MCP validate
    (tmp_path / "done.yaml").write_text("tasks: []", encoding="utf-8")
    bad_val = handle_mcp_request(
        {
            "id": 12,
            "method": "tools/call",
            "params": {"name": "donegate_validate", "arguments": {}},
        },
        tmp_path,
    )
    assert bad_val is not None
    assert json.loads(bad_val["result"]["content"][0]["text"])["valid"] is False


def test_agent_skill_and_plugin_manifests(tmp_path: Path) -> None:
    from donegate.integrations import apply_integration

    root = Path(__file__).resolve().parents[1]
    for skill_file in (root / "SKILL.md", root / "skills" / "donegate" / "SKILL.md"):
        text = skill_file.read_text(encoding="utf-8")
        assert text.startswith("---\nname: donegate\n")

    plugin_json = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin_json["name"] == "donegate"
    assert "mcp" in plugin_json["mcpServers"]["donegate"]["args"]
    assert runner.invoke(app, ["mcp", "--help"]).exit_code == 0
    market_json = json.loads(
        (root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert market_json["plugins"][0]["name"] == "donegate"

    res = apply_integration(tmp_path, "skill")
    assert (tmp_path / res.files_written[0]).is_file()
