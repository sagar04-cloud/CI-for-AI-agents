"""Tests for Phase 4 git-based scope guard."""

from __future__ import annotations

import subprocess
from pathlib import Path

from donegate.contract.models import ScopeMode, ScopeSpec
from donegate.scope import check_scope, match_glob, snapshot_baseline


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "secret.env").write_text("KEY=1\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    return tmp_path


def test_glob_match_cross_platform_and_braces() -> None:
    assert match_glob("src/api/auth.ts", "src/**/*.{js,ts}")
    assert match_glob("src\\api\\auth.ts", "src/**/*.ts")
    assert not match_glob("docs/readme.md", "src/**/*.ts")


def test_in_scope_and_ignored_lockfile(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    baseline = snapshot_baseline(repo)

    (repo / "src" / "app.py").write_text("print('updated')\n", encoding="utf-8")
    (repo / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (repo / "skills-lock.json").write_text("{}\n", encoding="utf-8")
    (repo / ".agents" / "skills" / "donegate").mkdir(parents=True)
    (repo / ".agents" / "skills" / "donegate" / "SKILL.md").write_text("x\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "pkg.js").write_text("x\n", encoding="utf-8")

    scope = ScopeSpec(allow=["src/**/*.py"])
    res = check_scope(repo, scope, mode=ScopeMode.BLOCK, baseline=baseline)
    assert res.passed is True
    assert "package-lock.json" in res.ignored_files
    assert "skills-lock.json" in res.ignored_files
    assert ".agents/skills/donegate/SKILL.md" in res.ignored_files
    assert "node_modules/pkg.js" in res.ignored_files


def test_out_of_scope_untracked_and_deny(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    baseline = snapshot_baseline(repo)

    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    (repo / "notes.txt").write_text("untracked\n", encoding="utf-8")

    scope = ScopeSpec(allow=["src/**/*.py"], deny=["README.md"])
    res = check_scope(repo, scope, mode=ScopeMode.BLOCK, baseline=baseline)
    assert res.passed is False
    assert "README.md" in res.out_of_scope_files
    assert "notes.txt" in res.out_of_scope_files
    assert any("git restore" in cmd for cmd in res.revert_commands)
    assert any("git clean" in cmd for cmd in res.revert_commands)


def test_deleted_and_renamed_files(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    baseline = snapshot_baseline(repo)

    (repo / "secret.env").unlink()
    _git(repo, "mv", "README.md", "docs_readme.md")

    scope = ScopeSpec(allow=["src/**/*.py"])
    res = check_scope(repo, scope, mode=ScopeMode.REVERT_SUGGESTION, baseline=baseline)
    assert res.passed is True  # revert-suggestion does not block
    assert "secret.env" in res.out_of_scope_files
    assert "docs_readme.md" in res.out_of_scope_files
    assert len(res.revert_commands) >= 2


def test_warn_mode_allows_passing(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    baseline = snapshot_baseline(repo)
    (repo / "README.md").write_text("# Warn\n", encoding="utf-8")

    res = check_scope(repo, ScopeSpec(allow=["src/**"]), mode=ScopeMode.WARN, baseline=baseline)
    assert res.passed is True
    assert res.out_of_scope_files == ["README.md"]
