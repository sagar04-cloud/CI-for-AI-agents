"""Zero-dependency HTTP dashboard for DoneGate run state and event logs."""

from __future__ import annotations

import html
import http.server
import json
from pathlib import Path

from donegate.supervisor.state import load_state, read_events


def render_dashboard_html(repo_root: Path) -> str:
    """Render a self-contained HTML dashboard from .donegate/state.json and events.log."""
    state = load_state(repo_root)
    events = read_events(repo_root)[-50:]
    goal = html.escape(state.goal) if state else "No active contract run (.donegate/state.json)"

    rows: list[str] = []
    if state:
        for task_id, rt in state.tasks.items():
            badge = html.escape(rt.status.value)
            rows.append(
                "<tr>"
                f"<td><code>{html.escape(task_id)}</code></td>"
                f"<td><span class='badge badge-{badge}'>{badge}</span></td>"
                f"<td>{rt.usage.steps}</td>"
                f"<td>{rt.usage.retries}</td>"
                f"<td>{rt.usage.tokens}</td>"
                f"<td>{html.escape(rt.last_summary or '-')}</td>"
                "</tr>"
            )

    event_items = [
        f"<li><code>{html.escape(ev.timestamp.isoformat())}</code> "
        f"<strong>{html.escape(ev.event)}</strong> "
        f"({html.escape(ev.task_id or '-')}) -> {html.escape(ev.status or '-')}</li>"
        for ev in reversed(events)
    ]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>DoneGate Dashboard</title>
  <style>
    body {{
      font-family: system-ui, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0;
    }}
    h1, h2 {{ color: #38bdf8; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; background: #1e293b; }}
    th, td {{ padding: 0.65rem; border: 1px solid #334155; text-align: left; }}
    .badge {{
      padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.85rem; background: #334155;
    }}
    .badge-done {{ background: #166534; color: #dcfce7; }}
    .badge-failed {{ background: #991b1b; color: #fee2e2; }}
    .badge-in_progress {{ background: #1d4ed8; color: #dbeafe; }}
    ul {{ background: #1e293b; padding: 1rem 1.5rem; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>DoneGate Dashboard</h1>
  <p><strong>Goal:</strong> {goal}</p>
  <h2>Tasks</h2>
  <table>
    <thead>
      <tr>
        <th>Task ID</th><th>Status</th><th>Steps</th>
        <th>Retries</th><th>Tokens</th><th>Summary</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows) or "<tr><td colspan='6'>No tasks recorded yet.</td></tr>"}
    </tbody>
  </table>
  <h2>Recent Events</h2>
  <ul id="events">{"".join(event_items) or "<li>No events logged yet.</li>"}</ul>
  <script>
    setInterval(async () => {{
      try {{
        const s = await fetch('/api/state').then(r => r.json());
        if (s && s.tasks) {{
          document.title = 'DoneGate (' + Object.keys(s.tasks).length + ' tasks)';
        }}
      }} catch (_) {{}}
    }}, 3000);
  </script>
</body>
</html>
"""


def handle_ui_route(repo_root: Path, path: str) -> tuple[int, str, bytes]:
    """Resolve an HTTP GET route for the DoneGate UI."""
    resolved = repo_root.resolve()
    if path == "/api/state":
        state = load_state(resolved)
        body = (
            state.model_dump_json(indent=2) if state else json.dumps({"tasks": {}})
        ).encode("utf-8")
        return 200, "application/json", body
    if path == "/api/events":
        events = [e.model_dump(mode="json") for e in read_events(resolved)]
        return 200, "application/json", json.dumps(events, indent=2).encode("utf-8")
    return 200, "text/html; charset=utf-8", render_dashboard_html(resolved).encode("utf-8")


def create_ui_server(
    repo_root: Path, host: str = "127.0.0.1", port: int = 8765
) -> http.server.ThreadingHTTPServer:
    """Create a ThreadingHTTPServer serving the DoneGate dashboard and JSON APIs."""
    resolved = repo_root.resolve()

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            code, content_type, body = handle_ui_route(resolved, self.path)
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return http.server.ThreadingHTTPServer((host, port), _Handler)
