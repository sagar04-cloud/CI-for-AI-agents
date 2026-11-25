"""Base types, plugin registry, and compact failure summary for DoneGate checks."""

from __future__ import annotations

import time
from collections.abc import Callable
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from donegate.contract.models import CheckSpec, Criticality, TaskSpec


class CheckResult(BaseModel):
    """Normalized outcome of running a single check."""

    passed: bool
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    tokens_cost: int = 0
    check_name: str = ""
    check_type: str = ""
    duration_seconds: float = 0.0
    suggested_action: str = ""


class CheckContext(BaseModel):
    """Execution context passed to every check handler."""

    repo_root: Path
    task_id: str = ""
    criticality: Criticality = Criticality.MUST
    human_approvals: set[str] = Field(default_factory=set)
    lint_baselines: dict[str, int] = Field(default_factory=dict)
    llm_judge_hook: Callable[[CheckSpec, Path], tuple[bool, str]] | None = None


class CheckHandler(Protocol):
    """Protocol for check plugins."""

    check_type: str

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        """Execute the check and return a CheckResult."""
        ...


class CheckRegistry:
    """Registry of built-in and entry-point check handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, CheckHandler] = {}

    def register(self, check_type: str, handler: CheckHandler) -> None:
        """Register a handler for a check type."""
        self._handlers[check_type.lower()] = handler

    def get(self, check_type: str) -> CheckHandler:
        """Look up a check handler by type."""
        key = check_type.lower()
        if key not in self._handlers:
            available = ", ".join(sorted(self._handlers))
            raise KeyError(f"Unknown check type {check_type!r}. Available: {available}")
        return self._handlers[key]

    def list_types(self) -> list[str]:
        """Return sorted list of registered check types."""
        return sorted(self._handlers)

    def load_entry_points(self, group: str = "donegate.checks") -> None:
        """Load third-party checks from Python entry_points."""
        for ep in entry_points(group=group):
            loaded = ep.load()
            handler = loaded() if callable(loaded) and not hasattr(loaded, "run") else loaded
            self.register(ep.name, handler)


_DEFAULT_CHECK_REGISTRY: CheckRegistry | None = None


def get_check_registry() -> CheckRegistry:
    """Return the global check registry populated with built-ins and entry points."""
    global _DEFAULT_CHECK_REGISTRY
    if _DEFAULT_CHECK_REGISTRY is None:
        from donegate.checks.builtins import register_builtin_checks

        registry = CheckRegistry()
        register_builtin_checks(registry)
        registry.load_entry_points()
        _DEFAULT_CHECK_REGISTRY = registry
    return _DEFAULT_CHECK_REGISTRY


def run_checks(
    task: TaskSpec,
    context: CheckContext,
    registry: CheckRegistry | None = None,
) -> list[CheckResult]:
    """Run all checks configured on a task and return their CheckResults."""
    reg = registry or get_check_registry()
    results: list[CheckResult] = []
    for spec in task.checks:
        if (
            spec.type == "llm_judge"
            and task.criticality == Criticality.MUST
            and len(task.checks) == 1
        ):
            results.append(
                CheckResult(
                    passed=False,
                    message="llm_judge cannot be the sole check on a must task",
                    check_name=spec.display_name(),
                    check_type=spec.type,
                    suggested_action="Add an objective check (e.g., test_suite or command).",
                )
            )
            continue

        handler = reg.get(spec.type)
        started = time.monotonic()
        res = handler.run(spec, context)
        res.duration_seconds = round(time.monotonic() - started, 3)
        res.check_name = res.check_name or spec.display_name()
        res.check_type = res.check_type or spec.type
        results.append(res)
    return results


def format_failure_summary(results: list[CheckResult], max_lines: int = 15) -> str:
    """Format a compact (<=15 lines) failure summary for AI agents."""
    failing = [r for r in results if not r.passed]
    if not failing:
        return "All checks passed."

    lines: list[str] = [f"FAILED ({len(failing)} check(s) failed):"]
    for res in failing:
        lines.append(f"- [{res.check_name}] {res.message}")
        err_lines = res.evidence.get("key_error_lines") or res.evidence.get("stderr_tail") or []
        for err in err_lines[:4]:
            lines.append(f"  {str(err)[:160]}")
        if res.suggested_action:
            lines.append(f"  Next: {res.suggested_action}")
        if len(lines) >= max_lines - 1:
            break

    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + ["  ... (truncated; see .donegate/events.log)"]
    return "\n".join(lines[:max_lines])
