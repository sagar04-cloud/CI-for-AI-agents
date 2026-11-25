"""Local web dashboard (`donegate ui`) reading .donegate/state.json and events.log."""

from __future__ import annotations

from donegate.ui.server import create_ui_server, handle_ui_route, render_dashboard_html

__all__ = ["create_ui_server", "handle_ui_route", "render_dashboard_html"]
