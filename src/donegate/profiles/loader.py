"""Load language profiles, auto-detect project languages, and generate done.yaml."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

import yaml

from donegate.contract.models import (
    BudgetSpec,
    CheckSpec,
    Contract,
    ProfileBinding,
    ScopeSpec,
    TaskSpec,
)
from donegate.profiles.models import LanguageProfile

_SKIP_DIRS = {
    ".git",
    ".donegate",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "dist",
    "build",
    "bin",
    "obj",
    "vendor",
    "__pycache__",
}


@dataclass(frozen=True)
class DetectedProfile:
    """A language profile matched at a relative directory inside a repo."""

    profile: LanguageProfile
    rel_path: str = "."


def builtin_profiles_dir() -> Path:
    """Locate the built-in profiles directory (works in editable & packaged installs)."""
    pkg_data = Path(__file__).resolve().parent / "data"
    if pkg_data.is_dir() and any(pkg_data.glob("*.yaml")):
        return pkg_data
    repo_profiles = Path(__file__).resolve().parents[3] / "profiles"
    if repo_profiles.is_dir():
        return repo_profiles
    return pkg_data


def load_all_profiles(repo_root: Path | None = None) -> dict[str, LanguageProfile]:
    """Load built-in profiles and merge any repo-local overrides."""
    profiles: dict[str, LanguageProfile] = {}
    search_dirs: list[Path] = [builtin_profiles_dir()]
    if repo_root is not None:
        search_dirs.append(repo_root / "profiles")
        search_dirs.append(repo_root / ".donegate" / "profiles")

    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for yaml_file in sorted(directory.glob("*.yaml")):
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                prof = LanguageProfile.model_validate(raw)
                profiles[prof.name.lower()] = prof
    return profiles


def _matches_detection_file(directory: Path, marker: str) -> bool:
    if any(ch in marker for ch in "*?[]"):
        return any(fnmatch.fnmatch(item.name, marker) for item in directory.iterdir())
    return (directory / marker).exists()


def detect_profiles(
    repo_root: Path,
    profiles: dict[str, LanguageProfile] | None = None,
    max_depth: int = 2,
) -> list[DetectedProfile]:
    """Detect one or more language profiles across a repository (supports monorepos)."""
    all_profiles = profiles or load_all_profiles(repo_root)
    detected: list[DetectedProfile] = []
    seen_pairs: set[tuple[str, str]] = set()

    def scan(directory: Path, depth: int) -> None:
        rel = directory.relative_to(repo_root).as_posix() if directory != repo_root else "."
        for prof in all_profiles.values():
            if any(_matches_detection_file(directory, m) for m in prof.detection_files):
                key = (prof.name, rel)
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    detected.append(DetectedProfile(profile=prof, rel_path=rel))
        if depth >= max_depth:
            return
        for child in sorted(directory.iterdir()):
            if child.is_dir() and child.name not in _SKIP_DIRS and not child.name.startswith("."):
                scan(child, depth + 1)

    scan(repo_root, 0)
    return detected


def _prefix_globs(globs: list[str], rel_path: str) -> list[str]:
    if rel_path == ".":
        return list(globs)
    return [f"{rel_path}/{g}" for g in globs]


def generate_contract(
    repo_root: Path,
    goal: str = "Complete task safely within DoneGate contract",
    template_profile: str | None = None,
) -> Contract:
    """Auto-detect project languages and generate a pre-filled done.yaml Contract."""
    all_profiles = load_all_profiles(repo_root)
    if template_profile:
        key = template_profile.lower()
        if key not in all_profiles:
            raise KeyError(f"Unknown profile {template_profile!r}")
        detected = [DetectedProfile(profile=all_profiles[key], rel_path=".")]
    else:
        detected = detect_profiles(repo_root, all_profiles)

    if not detected:
        return Contract(
            goal=goal,
            tasks=[
                TaskSpec(
                    id="main-task",
                    title=goal,
                    scope=ScopeSpec(allow=["**/*"], deny=[".git/**"]),
                    budget=BudgetSpec(steps=20, minutes=30),
                    checks=[CheckSpec(type="command", name="verify", command="echo ok")],
                )
            ],
        )

    tasks: list[TaskSpec] = []
    bindings: list[ProfileBinding] = []
    for idx, item in enumerate(detected):
        prof = item.profile
        bindings.append(ProfileBinding(profile=prof.name, path=item.rel_path))
        prefix = "" if item.rel_path == "." else f"cd {item.rel_path} && "
        checks: list[CheckSpec] = [
            CheckSpec(
                type="test_suite",
                name=f"{prof.name}-tests",
                command=f"{prefix}{prof.default_test_command}",
                parser=prof.test_parser,
            )
        ]
        if prof.lint_command:
            checks.append(
                CheckSpec(
                    type="lint_clean",
                    name=f"{prof.name}-lint",
                    command=f"{prefix}{prof.lint_command}",
                )
            )
        allow_globs = _prefix_globs(
            prof.default_scope.source + prof.default_scope.tests, item.rel_path
        )
        deny_globs = _prefix_globs(prof.default_scope.ignore, item.rel_path)
        task_id = f"{prof.name}-task" if len(detected) == 1 else f"{prof.name}-{idx + 1}"
        tasks.append(
            TaskSpec(
                id=task_id,
                title=f"Implement and verify {prof.display_name or prof.name} changes",
                scope=ScopeSpec(allow=allow_globs or ["**/*"], deny=deny_globs),
                budget=BudgetSpec(steps=20, minutes=30),
                checks=checks,
            )
        )

    lang_field: str | list[str] = (
        detected[0].profile.name
        if len(detected) == 1
        else [d.profile.name for d in detected]
    )
    return Contract(
        goal=goal,
        language_profile=lang_field,
        profiles=bindings,
        tasks=tasks,
    )
