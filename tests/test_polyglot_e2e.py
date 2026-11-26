"""Live end-to-end tests against real Node.js, Go, and Rust toolchains."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from donegate.cli import app

runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def _init_git_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.email", "ci@donegate.dev")
    _git(repo, "config", "user.name", "DoneGate CI")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_live_node_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "package.json").write_text(
        '{"name":"demo","scripts":{"test":"node --test"}}\n', encoding="utf-8"
    )
    (tmp_path / "sum.mjs").write_text("export const add = (a, b) => a - b;\n", encoding="utf-8")
    (tmp_path / "sum.test.mjs").write_text(
        "import test from 'node:test';\n"
        "import assert from 'node:assert/strict';\n"
        "import { add } from './sum.mjs';\n"
        "test('adds', () => assert.equal(add(2, 3), 5));\n",
        encoding="utf-8",
    )
    (tmp_path / "done.yaml").write_text(
        """version: "1"
goal: "Fix Node add()"
language_profile: node
tasks:
  - id: node-task
    title: "Fix sum.mjs"
    scope:
      allow: ["*.mjs", "package.json"]
    checks:
      - type: test_suite
        command: "node --test"
        parser: tap
""",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["start", "node-task"]).exit_code == 0
    assert runner.invoke(app, ["check", "node-task"]).exit_code == 1
    (tmp_path / "sum.mjs").write_text("export const add = (a, b) => a + b;\n", encoding="utf-8")
    assert runner.invoke(app, ["check", "node-task"]).exit_code == 0


@pytest.mark.skipif(shutil.which("go") is None, reason="go not installed")
def test_live_go_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "go.mod").write_text("module example.com/demo\n\ngo 1.21\n", encoding="utf-8")
    (tmp_path / "math.go").write_text(
        "package demo\n\nfunc Add(a, b int) int { return a - b }\n", encoding="utf-8"
    )
    (tmp_path / "math_test.go").write_text(
        "package demo\n\nimport \"testing\"\n\n"
        "func TestAdd(t *testing.T) { if Add(2, 3) != 5 { t.Fatal(\"bad\") } }\n",
        encoding="utf-8",
    )
    (tmp_path / "done.yaml").write_text(
        """version: "1"
goal: "Fix Go Add()"
language_profile: go
tasks:
  - id: go-task
    title: "Fix math.go"
    scope:
      allow: ["*.go", "go.mod"]
    checks:
      - type: test_suite
        command: "go test -json ./..."
        parser: go_test
""",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["start", "go-task"]).exit_code == 0
    assert runner.invoke(app, ["check", "go-task"]).exit_code == 1
    (tmp_path / "math.go").write_text(
        "package demo\n\nfunc Add(a, b int) int { return a + b }\n", encoding="utf-8"
    )
    assert runner.invoke(app, ["check", "go-task"]).exit_code == 0


@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo not installed")
def test_live_rust_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n', encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text(
        "pub fn add(a: i32, b: i32) -> i32 { a - b }\n"
        "#[cfg(test)]\nmod tests {\n"
        "    use super::*;\n"
        "    #[test]\n    fn it_works() { assert_eq!(add(2, 3), 5); }\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "done.yaml").write_text(
        """version: "1"
goal: "Fix Rust add()"
language_profile: rust
tasks:
  - id: rust-task
    title: "Fix src/lib.rs"
    scope:
      allow: ["src/**/*.rs", "Cargo.toml"]
    checks:
      - type: test_suite
        command: "cargo test"
        parser: cargo_test
""",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "init")

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["start", "rust-task"]).exit_code == 0
    assert runner.invoke(app, ["check", "rust-task"]).exit_code == 1
    (tmp_path / "src" / "lib.rs").write_text(
        "pub fn add(a: i32, b: i32) -> i32 { a + b }\n"
        "#[cfg(test)]\nmod tests {\n"
        "    use super::*;\n"
        "    #[test]\n    fn it_works() { assert_eq!(add(2, 3), 5); }\n"
        "}\n",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["check", "rust-task"]).exit_code == 0
