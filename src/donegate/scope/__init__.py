"""Git-based scope guard for DoneGate."""

from __future__ import annotations

from donegate.scope.glob_match import match_glob
from donegate.scope.guard import (
    ChangedFile,
    GitBaseline,
    ScopeCheckResult,
    check_scope,
    snapshot_baseline,
)

__all__ = [
    "ChangedFile",
    "GitBaseline",
    "ScopeCheckResult",
    "check_scope",
    "match_glob",
    "snapshot_baseline",
]
