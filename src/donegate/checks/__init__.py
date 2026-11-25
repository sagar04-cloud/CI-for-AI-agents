"""Language-agnostic check engine, plugin registry, and compact agent feedback."""

from __future__ import annotations

from donegate.checks.base import (
    CheckContext,
    CheckHandler,
    CheckRegistry,
    CheckResult,
    format_failure_summary,
    get_check_registry,
    run_checks,
)
from donegate.checks.builtins import register_builtin_checks

__all__ = [
    "CheckContext",
    "CheckHandler",
    "CheckRegistry",
    "CheckResult",
    "format_failure_summary",
    "get_check_registry",
    "register_builtin_checks",
    "run_checks",
]
