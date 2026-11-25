"""Tests for Phase 3 language profiles and polyglot auto-detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from donegate.profiles import detect_profiles, generate_contract, load_all_profiles


@pytest.mark.parametrize(
    ("profile_name", "marker_file", "expected_parser"),
    [
        ("python", "pyproject.toml", "pytest"),
        ("node", "package.json", "jest"),
        ("go", "go.mod", "go_test"),
        ("rust", "Cargo.toml", "cargo_test"),
        ("java", "pom.xml", "junit_xml"),
        ("dotnet", "App.csproj", "junit_xml"),
        ("ruby", "Gemfile", "generic"),
        ("php", "composer.json", "junit_xml"),
    ],
)
def test_detect_each_language_profile(
    tmp_path: Path, profile_name: str, marker_file: str, expected_parser: str
) -> None:
    (tmp_path / marker_file).write_text("", encoding="utf-8")
    detected = detect_profiles(tmp_path)
    names = [d.profile.name for d in detected]
    assert profile_name in names

    contract = generate_contract(tmp_path, goal="Test project")
    test_checks = [c for c in contract.tasks[0].checks if c.type == "test_suite"]
    assert len(test_checks) == 1
    assert test_checks[0].parser == expected_parser


def test_monorepo_polyglot_detection(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "go.mod").write_text("module example.com/api\n", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text('{"name":"web"}', encoding="utf-8")

    detected = detect_profiles(tmp_path)
    pairs = {(d.profile.name, d.rel_path) for d in detected}
    assert ("go", "backend") in pairs
    assert ("node", "frontend") in pairs

    contract = generate_contract(tmp_path, goal="Polyglot feature")
    assert len(contract.tasks) == 2
    assert len(contract.profiles) == 2


def test_user_profile_override(tmp_path: Path) -> None:
    custom_dir = tmp_path / ".donegate" / "profiles"
    custom_dir.mkdir(parents=True)
    (custom_dir / "python.yaml").write_text(
        """
name: python
display_name: Custom Python
detection_files: [pyproject.toml]
default_test_command: pytest -n auto
test_parser: pytest
""",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    profiles = load_all_profiles(tmp_path)
    assert profiles["python"].default_test_command == "pytest -n auto"
    contract = generate_contract(tmp_path)
    assert contract.tasks[0].checks[0].command == "pytest -n auto"
