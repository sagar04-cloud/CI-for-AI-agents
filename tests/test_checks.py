"""Tests for Phase 2 language-agnostic check engine and built-in checks."""

from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from donegate.checks import (
    CheckContext,
    CheckResult,
    format_failure_summary,
    get_check_registry,
    run_checks,
)
from donegate.contract.models import CheckSpec, Criticality, TaskSpec


def test_command_check_pass_and_fail(tmp_path: Path) -> None:
    reg = get_check_registry()
    ctx = CheckContext(repo_root=tmp_path)

    ok_spec = CheckSpec(type="command", command=f'"{sys.executable}" -c "print(123)"')
    assert reg.get("command").run(ok_spec, ctx).passed is True

    bad_spec = CheckSpec(type="command", command=f'"{sys.executable}" -c "import sys; sys.exit(2)"')
    res = reg.get("command").run(bad_spec, ctx)
    assert res.passed is False
    assert res.tokens_cost == 0


def test_test_suite_check_with_pytest_output(tmp_path: Path) -> None:
    reg = get_check_registry()
    ctx = CheckContext(repo_root=tmp_path)
    cmd = f'"{sys.executable}" -c "print(\'2 passed in 0.01s\')"'
    spec = CheckSpec(type="test_suite", command=cmd, parser="pytest")
    res = reg.get("test_suite").run(spec, ctx)
    assert res.passed is True
    assert res.evidence["passed"] == 2


def test_file_exists_and_contains(tmp_path: Path) -> None:
    reg = get_check_registry()
    ctx = CheckContext(repo_root=tmp_path)
    target = tmp_path / "hello.txt"
    target.write_text("version = 1.2.3\n", encoding="utf-8")

    assert reg.get("file_exists").run(CheckSpec(type="file_exists", path="hello.txt"), ctx).passed
    missing_res = reg.get("file_exists").run(
        CheckSpec(type="file_exists", path="missing.txt"), ctx
    )
    assert not missing_res.passed

    assert reg.get("file_contains").run(
        CheckSpec(type="file_contains", path="hello.txt", pattern=r"1\.2\.3"), ctx
    ).passed
    assert reg.get("file_contains").run(
        CheckSpec(type="file_contains", path="hello.txt", pattern=r"TODO", negate=True), ctx
    ).passed


def test_json_path_check(tmp_path: Path) -> None:
    reg = get_check_registry()
    ctx = CheckContext(repo_root=tmp_path)
    (tmp_path / "pkg.json").write_text(
        json.dumps({"name": "demo", "scripts": {"test": "vitest"}}), encoding="utf-8"
    )
    assert reg.get("json_path").run(
        CheckSpec(type="json_path", path="pkg.json", json_path="$.scripts.test", equals="vitest"),
        ctx,
    ).passed
    assert not reg.get("json_path").run(
        CheckSpec(type="json_path", path="pkg.json", json_path="$.missing"),
        ctx,
    ).passed


def test_http_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResp:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._buf = io.BytesIO(body)

        def read(self) -> bytes:
            return self._buf.read()

        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    def _fake_urlopen(req: object, timeout: int = 120) -> _FakeResp:
        return _FakeResp(200, b"healthy")

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    reg = get_check_registry()
    ctx = CheckContext(repo_root=tmp_path)
    res = reg.get("http_check").run(
        CheckSpec(
            type="http_check",
            url="http://127.0.0.1:8000/health",
            expected_status=200,
            body_contains="healthy",
        ),
        ctx,
    )
    assert res.passed is True

    bad = reg.get("http_check").run(
        CheckSpec(
            type="http_check",
            url="http://127.0.0.1:8000/health",
            expected_status=201,
        ),
        ctx,
    )
    assert bad.passed is False


def test_lint_clean_and_no_new_lint_errors(tmp_path: Path) -> None:
    reg = get_check_registry()
    ctx = CheckContext(repo_root=tmp_path)
    ok_cmd = f'"{sys.executable}" -c "print(\'ok\')"'
    two_err_cmd = f'"{sys.executable}" -c "import sys; print(\'e1\\ne2\'); sys.exit(1)"'

    assert reg.get("lint_clean").run(CheckSpec(type="lint_clean", command=ok_cmd), ctx).passed
    lint_fail = reg.get("lint_clean").run(CheckSpec(type="lint_clean", command=two_err_cmd), ctx)
    assert not lint_fail.passed

    assert reg.get("no_new_lint_errors").run(
        CheckSpec(type="no_new_lint_errors", command=two_err_cmd, baseline_errors=2), ctx
    ).passed
    assert not reg.get("no_new_lint_errors").run(
        CheckSpec(type="no_new_lint_errors", command=two_err_cmd, baseline_errors=1), ctx
    ).passed


def _git(repo: Path, *args: str) -> None:
    import subprocess

    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def test_no_new_lint_errors_diff_aware(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "app.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")

    # Modify line 2 only; error on untouched line 1 should pass, error on line 2 should fail
    (tmp_path / "app.py").write_text("a = 1\nb = 3\n", encoding="utf-8")
    reg = get_check_registry()
    ctx = CheckContext(repo_root=tmp_path)

    untouched_err = (
        f'"{sys.executable}" -c "import sys; print(\'app.py:1:1: E999 old\'); sys.exit(1)"'
    )
    assert reg.get("no_new_lint_errors").run(
        CheckSpec(type="no_new_lint_errors", command=untouched_err, diff_aware=True), ctx
    ).passed

    new_err = f'"{sys.executable}" -c "import sys; print(\'app.py:2:1: E999 new\'); sys.exit(1)"'
    assert not reg.get("no_new_lint_errors").run(
        CheckSpec(type="no_new_lint_errors", command=new_err, diff_aware=True), ctx
    ).passed


def test_human_approval_and_llm_judge(tmp_path: Path) -> None:
    reg = get_check_registry()
    ctx_wait = CheckContext(repo_root=tmp_path, task_id="t1")
    assert not reg.get("human_approval").run(CheckSpec(type="human_approval"), ctx_wait).passed

    ctx_ok = CheckContext(
        repo_root=tmp_path,
        task_id="t1",
        human_approvals={"t1"},
        llm_judge_hook=lambda _s, _p: (True, "LGTM"),
    )
    assert reg.get("human_approval").run(CheckSpec(type="human_approval"), ctx_ok).passed
    assert reg.get("llm_judge").run(CheckSpec(type="llm_judge"), ctx_ok).passed


def test_run_checks_and_compact_failure_summary(tmp_path: Path) -> None:
    task = TaskSpec(
        id="t1",
        title="Demo",
        criticality=Criticality.MUST,
        checks=[
            CheckSpec(
                type="command",
                name="unit",
                command=f'"{sys.executable}" -c "import sys; print(\'err1\\nerr2\'); sys.exit(1)"',
            ),
            CheckSpec(type="file_exists", name="readme", path="README.md"),
        ],
    )
    results = run_checks(task, CheckContext(repo_root=tmp_path))
    assert len(results) == 2
    assert all(isinstance(r, CheckResult) and not r.passed for r in results)

    summary = format_failure_summary(results, max_lines=15)
    assert len(summary.splitlines()) <= 15
    assert "FAILED" in summary
