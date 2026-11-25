"""Goal-to-contract planner (deterministic offline heuristic + optional LLM hook)."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path

from donegate.contract.loader import parse_contract_yaml
from donegate.contract.models import (
    BudgetSpec,
    CheckSpec,
    Contract,
    Criticality,
    ScopeSpec,
    TaskSpec,
)
from donegate.profiles.loader import detect_profiles, generate_contract

PlannerHook = Callable[[str, Path], str]


def _slugify(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:32] or fallback


def _heuristic_plan(goal: str, repo_root: Path) -> Contract:
    """Break a natural-language goal into ordered implement + verify tasks."""
    base = generate_contract(repo_root, goal=goal)
    detected = detect_profiles(repo_root)

    if not detected:
        return base

    tasks: list[TaskSpec] = []
    prev_id: str | None = None
    for idx, item in enumerate(detected):
        prof = item.profile
        prefix = "" if item.rel_path == "." else f"cd {item.rel_path} && "
        impl_id = _slugify(f"{prof.name}-implement", f"impl-{idx + 1}")
        verify_id = _slugify(f"{prof.name}-verify", f"verify-{idx + 1}")

        allow_src = [
            f"{item.rel_path}/{g}" if item.rel_path != "." else g
            for g in (prof.default_scope.source or ["**/*"])
        ]
        allow_tests = [
            f"{item.rel_path}/{g}" if item.rel_path != "." else g
            for g in (prof.default_scope.tests or ["tests/**/*"])
        ]
        deny_globs = [
            f"{item.rel_path}/{g}" if item.rel_path != "." else g
            for g in prof.default_scope.ignore
        ]

        impl_task = TaskSpec(
            id=impl_id,
            title=f"Implement {prof.display_name or prof.name} changes for: {goal}",
            depends_on=[prev_id] if prev_id else [],
            priority=90 - idx * 10,
            criticality=Criticality.MUST,
            scope=ScopeSpec(allow=allow_src + allow_tests, deny=deny_globs),
            budget=BudgetSpec(steps=15, minutes=20, tokens=30000),
            checks=[
                CheckSpec(
                    type="test_suite",
                    name=f"{prof.name}-tests",
                    command=f"{prefix}{prof.default_test_command}",
                    parser=prof.test_parser,
                )
            ],
        )
        tasks.append(impl_task)

        verify_checks: list[CheckSpec] = [
            CheckSpec(
                type="test_suite",
                name=f"{prof.name}-full-tests",
                command=f"{prefix}{prof.default_test_command}",
                parser=prof.test_parser,
            )
        ]
        if prof.lint_command:
            verify_checks.append(
                CheckSpec(
                    type="lint_clean",
                    name=f"{prof.name}-lint",
                    command=f"{prefix}{prof.lint_command}",
                )
            )
        verify_task = TaskSpec(
            id=verify_id,
            title=f"Verify lint and tests for {prof.display_name or prof.name}",
            depends_on=[impl_id],
            priority=85 - idx * 10,
            criticality=Criticality.MUST,
            scope=ScopeSpec(allow=allow_src + allow_tests, deny=deny_globs),
            budget=BudgetSpec(steps=8, minutes=10, tokens=10000),
            checks=verify_checks,
        )
        tasks.append(verify_task)
        prev_id = verify_id

    return Contract(
        goal=goal,
        language_profile=base.language_profile,
        profiles=base.profiles,
        tasks=tasks,
    )


def draft_contract(
    goal: str,
    repo_root: Path,
    llm_hook: PlannerHook | None = None,
) -> Contract:
    """Draft a validated done.yaml Contract from a goal using an optional LLM hook."""
    if llm_hook is not None:
        raw_yaml = llm_hook(goal, repo_root)
        return parse_contract_yaml(raw_yaml)

    # Optional external planner command via env var DONEGATE_PLANNER_CMD
    env_cmd = os.environ.get("DONEGATE_PLANNER_CMD", "").strip()
    if env_cmd:
        import subprocess

        proc = subprocess.run(
            env_cmd,
            shell=True,
            cwd=str(repo_root),
            input=goal,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return parse_contract_yaml(proc.stdout)

    return _heuristic_plan(goal, repo_root)
