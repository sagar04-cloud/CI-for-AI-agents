"""Agent and git integrations for DoneGate."""

from __future__ import annotations

from donegate.integrations.generators import (
    SUPPORTED_INTEGRATIONS,
    IntegrationResult,
    apply_integration,
)
from donegate.integrations.mcp_server import handle_mcp_request, run_mcp_stdio

__all__ = [
    "IntegrationResult",
    "SUPPORTED_INTEGRATIONS",
    "apply_integration",
    "handle_mcp_request",
    "run_mcp_stdio",
]
