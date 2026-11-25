"""Tests validating all language example contracts and README quickstart."""

from __future__ import annotations

from pathlib import Path

from donegate.contract import load_contract

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def test_all_language_examples_are_valid_contracts() -> None:
    expected = {"python", "node", "go", "rust", "java", "dotnet", "ruby", "php"}
    found = {p.parent.name for p in EXAMPLES_DIR.glob("*/done.yaml")}
    assert expected.issubset(found)

    for yaml_file in sorted(EXAMPLES_DIR.glob("*/done.yaml")):
        contract = load_contract(yaml_file)
        assert len(contract.tasks) >= 1
