"""End-to-end CLI tests: init -> integrate -> start -> check -> fix -> status."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from donegate.cli import app

runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def test_cli_end_to_end_workflow(tmp_path: Path, monkeypatch: object) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "from src.app import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")

    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    # 1. init
    r_init = runner.invoke(app, ["init", "--json"])
    assert r_init.exit_code == 0
    assert json.loads(r_init.stdout)["ok"] is True

    # Override done.yaml with pytest-only check so ruff isn't required in temp repo
    py = sys.executable.replace("\\", "/")
    (tmp_path / "done.yaml").write_text(
        f"""
version: "1"
goal: "Fix add"
language_profile: python
tasks:
  - id: python-task
    title: "Fix add()"
    scope:
      allow: ["src/**/*.py", "tests/**/*.py"]
    checks:
      - type: test_suite
        command: '"{py}" -B -m pytest'
        parser: pytest
""",
        encoding="utf-8",
    )

    # 2. validate & integrate & doctor
    assert runner.invoke(app, ["validate", "--json"]).exit_code == 0
    assert runner.invoke(app, ["integrate", "generic", "--json"]).exit_code == 0
    assert runner.invoke(app, ["doctor", "--json"]).exit_code == 0

    # 3. next & start
    r_next = runner.invoke(app, ["next", "--json"])
    assert r_next.exit_code == 0
    assert json.loads(r_next.stdout)[0]["id"] == "python-task"
    assert runner.invoke(app, ["start", "python-task", "--json"]).exit_code == 0

    # 4. check (fail)
    r_fail = runner.invoke(app, ["check", "python-task", "--json"])
    assert r_fail.exit_code == 1
    assert json.loads(r_fail.stdout)["passed"] is False

    # 5. fix & check (pass)
    (tmp_path / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    r_pass = runner.invoke(app, ["check", "python-task", "--json"])
    assert r_pass.exit_code == 0, r_pass.stdout
    assert json.loads(r_pass.stdout)["passed"] is True

    # 6. status & log & export
    r_status = runner.invoke(app, ["status", "--json"])
    assert r_status.exit_code == 0
    assert json.loads(r_status.stdout)["tasks"]["python-task"]["status"] == "done"
    assert runner.invoke(app, ["log", "--json"]).exit_code == 0
    assert runner.invoke(app, ["export", "--schema"]).exit_code == 0
