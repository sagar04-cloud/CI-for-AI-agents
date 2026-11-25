"""Tests for feature/future enhancements and good-first-issue implementations."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from donegate.cli import app
from donegate.contract import export_contract_schema, load_contract
from donegate.integrations import apply_integration
from donegate.planner import draft_contract
from donegate.profiles import detect_profiles
from donegate.supervisor import Supervisor
from donegate.supervisor.otel import events_to_otlp_dict
from donegate.ui import handle_ui_route, render_dashboard_html

runner = CliRunner()


@pytest.mark.parametrize(
    ("profile_name", "marker"),
    [
        ("elixir", "mix.exs"),
        ("scala", "build.sbt"),
        ("swift", "Package.swift"),
        ("zig", "build.zig"),
        ("cpp", "CMakeLists.txt"),
    ],
)
def test_new_language_profiles_detected(tmp_path: Path, profile_name: str, marker: str) -> None:
    (tmp_path / marker).write_text("", encoding="utf-8")
    detected = detect_profiles(tmp_path)
    assert profile_name in [d.profile.name for d in detected]


def test_python_junitxml_example_valid() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "python-junitxml" / "done.yaml"
    contract = load_contract(example)
    assert contract.tasks[0].checks[0].parser == "junit_xml"


def test_new_integrations_and_claude_stop_hook(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    for name in ("aider", "openhands", "windsurf", "continue"):
        res = apply_integration(tmp_path, name)
        for rel in res.files_written:
            assert (tmp_path / rel).is_file()

    apply_integration(tmp_path, "claude_code")
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    stop_cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "donegate" in stop_cmd and "check" in stop_cmd


def test_planner_heuristic_and_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    contract = draft_contract("Add health endpoint", tmp_path)
    assert len(contract.tasks) == 2
    assert contract.tasks[1].depends_on == [contract.tasks[0].id]

    custom = draft_contract(
        "Custom",
        tmp_path,
        llm_hook=lambda g, _p: (
            f"goal: {g}\ntasks:\n  - id: t1\n    title: One\n"
            "    checks:\n      - type: command\n        command: echo ok\n"
        ),
    )
    assert custom.tasks[0].id == "t1"

    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["plan", "Build feature", "--json"])
    assert r.exit_code == 0
    assert (tmp_path / "done.yaml").is_file()
    assert runner.invoke(app, ["plan", "Again", "--json"]).exit_code == 1
    assert runner.invoke(app, ["plan", "Again", "--force"]).exit_code == 0

    # Test DONEGATE_PLANNER_CMD external command path
    import sys

    py_cmd = (
        f'"{sys.executable}" -c "print(\'goal: Env\\ntasks:\\n  - id: e1\\n'
        '    title: EnvTask\\n    checks:\\n      - type: command\\n        command: echo ok\')"'
    )
    monkeypatch.setenv("DONEGATE_PLANNER_CMD", py_cmd)
    env_contract = draft_contract("Env", tmp_path)
    assert env_contract.tasks[0].id == "e1"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def test_otel_export_ui_and_schema_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "a.txt").write_text("ok\n", encoding="utf-8")
    (tmp_path / "done.yaml").write_text(
        """
goal: "OTel & UI test"
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

    sup = Supervisor(tmp_path)
    sup.start("t1")
    sup.check("t1")

    otlp = events_to_otlp_dict(tmp_path)
    spans = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) >= 2

    html_doc = render_dashboard_html(tmp_path)
    assert "DoneGate Dashboard" in html_doc
    assert "t1" in html_doc

    code_s, ct_s, body_s = handle_ui_route(tmp_path, "/api/state")
    assert code_s == 200 and ct_s == "application/json" and "t1" in body_s.decode("utf-8")
    code_e, ct_e, body_e = handle_ui_route(tmp_path, "/api/events")
    assert code_e == 200 and ct_e == "application/json" and len(json.loads(body_e)) >= 2
    code_h, ct_h, _ = handle_ui_route(tmp_path, "/")
    assert code_h == 200 and "text/html" in ct_h

    schema = export_contract_schema()
    assert "$id" in schema and "description" in schema

    monkeypatch.chdir(tmp_path)
    r_otel = runner.invoke(app, ["export", "--otel"])
    assert r_otel.exit_code == 0
    assert "resourceSpans" in json.loads(r_otel.stdout)

    # Doctor hint on missing zig binary
    (tmp_path / "build.zig").write_text("", encoding="utf-8")
    r_doc = runner.invoke(app, ["doctor", "--json"])
    assert r_doc.exit_code == 0
    doc = json.loads(r_doc.stdout)
    assert any(t["tool"] == "zig" for t in doc["tools"])
