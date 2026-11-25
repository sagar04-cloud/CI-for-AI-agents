"""Tests for Phase 5 supervisor: lifecycle, retries, scope, budget, human gate, logs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from donegate.contract.models import TaskStatus
from donegate.supervisor import Supervisor, read_events


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def _setup_repo(tmp_path: Path, contract_yaml: str) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "src.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "done.yaml").write_text(contract_yaml, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def test_simulated_run_failure_retry_scope_budget_human(tmp_path: Path) -> None:
    py = sys.executable.replace("\\", "/")
    contract_yaml = f"""
version: "1"
goal: "Simulate full supervisor lifecycle"
deadline: "2020-01-01T00:00:00Z"
tasks:
  - id: fix-code
    title: "Fix src.py"
    priority: 100
    scope:
      allow: ["src.py"]
    budget:
      steps: 10
      minutes: 10
      tokens: 1000
    on_fail:
      strategy: retry
      max_retries: 2
    checks:
      - type: file_contains
        path: "src.py"
        pattern: "x = 2"
      - type: command
        command: '"{py}" -c "print(1)"'
  - id: human-gate
    title: "Human sign-off"
    depends_on: [fix-code]
    priority: 50
    needs_human_approval: true
    scope:
      allow: ["src.py"]
    checks:
      - type: file_exists
        path: "src.py"
  - id: budget-task
    title: "Budget limited"
    priority: 10
    budget:
      steps: 2
      tokens: 100
    checks:
      - type: file_exists
        path: "src.py"
"""
    repo = _setup_repo(tmp_path, contract_yaml)
    sup = Supervisor(repo)

    # 1. next() returns fix-code (highest priority, deps met)
    nxt = sup.next_tasks()
    assert nxt[0].id == "fix-code"

    # 2. start() fix-code and fail check + scope violation
    sup.start("fix-code")
    (repo / "other.py").write_text("y = 999\n", encoding="utf-8")
    fail_res = sup.check("fix-code")
    assert not fail_res.passed
    assert fail_res.status == TaskStatus.IN_PROGRESS
    assert fail_res.deadline_warning is not None
    assert "other.py" in (fail_res.scope_result.out_of_scope_files if fail_res.scope_result else [])

    # 3. Revert out-of-scope, fix src.py, and pass
    (repo / "other.py").write_text("y = 1\n", encoding="utf-8")
    (repo / "src.py").write_text("x = 2\n", encoding="utf-8")
    pass_res = sup.check("fix-code")
    assert pass_res.passed
    assert pass_res.status == TaskStatus.DONE

    # 4. human-gate is now runnable -> waits for approval -> passes once approved
    assert sup.next_tasks()[0].id == "human-gate"
    sup.start("human-gate")
    wait_res = sup.check("human-gate")
    assert not wait_res.passed
    assert wait_res.status == TaskStatus.AWAITING_HUMAN
    approved_res = sup.check("human-gate", approve=True)
    assert approved_res.passed
    assert approved_res.status == TaskStatus.DONE

    # 5. budget overrun
    sup.start("budget-task")
    _, overrun = sup.report_usage("budget-task", tokens=250)
    assert overrun is not None
    assert sup.state.tasks["budget-task"].status == TaskStatus.FAILED

    # 6. events.log recorded everything
    events = read_events(repo)
    event_names = [e.event for e in events]
    assert "task_started" in event_names
    assert "task_failed" in event_names
    assert "task_passed" in event_names
    assert "budget_overrun" not in event_names or "usage_reported" in event_names
    assert (repo / ".donegate" / "state.json").is_file()
