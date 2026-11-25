"""Tests for Phase 1 contract specification, validation, and JSON schema."""

from __future__ import annotations

from pathlib import Path

import pytest

from donegate.contract import (
    SCHEMA_VERSION,
    Contract,
    ContractValidationError,
    Criticality,
    TaskStatus,
    dump_contract,
    export_contract_schema,
    load_contract,
    parse_contract_yaml,
)


def _valid_yaml() -> str:
    return """
version: "1"
goal: "Fix authentication bug and add regression tests"
deadline: "2026-12-01T00:00:00Z"
language_profile: python
tasks:
  - id: fix-auth
    title: "Fix token expiry check"
    depends_on: []
    priority: 100
    scope:
      allow: ["src/auth/*.py"]
      deny: ["src/billing/**"]
    budget:
      steps: 10
      minutes: 15
      tokens: 20000
    checks:
      - type: test_suite
        command: "pytest tests/test_auth.py"
    on_fail:
      strategy: retry
      max_retries: 2
  - id: update-docs
    title: "Update auth docs"
    depends_on: [fix-auth]
    priority: 40
    criticality: should
    needs_human_approval: true
    scope:
      allow: ["docs/*.md"]
    checks:
      - type: file_exists
        path: "docs/auth.md"
"""


def test_parse_valid_contract() -> None:
    contract = parse_contract_yaml(_valid_yaml())
    assert isinstance(contract, Contract)
    assert contract.version == SCHEMA_VERSION
    assert len(contract.tasks) == 2
    assert contract.tasks[0].status == TaskStatus.PENDING
    assert contract.tasks[1].criticality == Criticality.SHOULD
    assert contract.tasks[1].needs_human_approval is True


def test_duplicate_task_ids_rejected() -> None:
    raw = """
goal: "Dup test"
tasks:
  - id: task-a
    title: "One"
    checks: [{type: command, command: "echo 1"}]
  - id: task-a
    title: "Two"
    checks: [{type: command, command: "echo 2"}]
"""
    with pytest.raises(ContractValidationError, match="Duplicate task IDs"):
        parse_contract_yaml(raw)


def test_unknown_dependency_rejected() -> None:
    raw = """
goal: "Unknown dep"
tasks:
  - id: task-a
    title: "One"
    depends_on: [does-not-exist]
    checks: [{type: command, command: "echo 1"}]
"""
    with pytest.raises(ContractValidationError, match="unknown task"):
        parse_contract_yaml(raw)


def test_cycle_detection_prints_cycle_path() -> None:
    raw = """
goal: "Cycle test"
tasks:
  - id: a
    title: "A"
    depends_on: [c]
    checks: [{type: command, command: "echo a"}]
  - id: b
    title: "B"
    depends_on: [a]
    checks: [{type: command, command: "echo b"}]
  - id: c
    title: "C"
    depends_on: [b]
    checks: [{type: command, command: "echo c"}]
"""
    with pytest.raises(ContractValidationError) as exc_info:
        parse_contract_yaml(raw)
    msg = str(exc_info.value)
    assert "Dependency cycle detected" in msg
    assert "->" in msg
    for node in ("a", "b", "c"):
        assert node in msg


def test_empty_checks_rejected() -> None:
    raw = """
goal: "No checks"
tasks:
  - id: t1
    title: "No checks"
    checks: []
"""
    with pytest.raises(ContractValidationError):
        parse_contract_yaml(raw)


def test_llm_judge_only_rejected() -> None:
    raw = """
goal: "Only LLM judge"
tasks:
  - id: t1
    title: "Only judge"
    checks:
      - type: llm_judge
        prompt: "Looks good?"
"""
    with pytest.raises(ContractValidationError, match="at least one objective check"):
        parse_contract_yaml(raw)


@pytest.mark.parametrize("bad_glob", ["", "   ", "src/[unclosed"])
def test_invalid_glob_rejected(bad_glob: str) -> None:
    raw = f"""
goal: "Bad glob"
tasks:
  - id: t1
    title: "Bad glob"
    scope:
      allow: ["{bad_glob}"]
    checks:
      - type: command
        command: "echo ok"
"""
    with pytest.raises(ContractValidationError):
        parse_contract_yaml(raw)


def test_dump_and_reload_contract(tmp_path: Path) -> None:
    contract = parse_contract_yaml(_valid_yaml())
    out_file = tmp_path / "done.yaml"
    dump_contract(contract, out_file)
    reloaded = load_contract(out_file)
    assert reloaded.goal == contract.goal
    assert [t.id for t in reloaded.tasks] == [t.id for t in contract.tasks]


def test_export_contract_schema() -> None:
    schema = export_contract_schema()
    assert schema["x-donegate-schema-version"] == SCHEMA_VERSION
    assert "$schema" in schema
    assert "tasks" in schema["properties"]
