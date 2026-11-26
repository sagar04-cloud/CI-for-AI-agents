"""Zero-network file generators for claude_code, cursor, git, generic, and mcp."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from pydantic import BaseModel, Field

from donegate import __version__
from donegate.contract.loader import atomic_write_text

SUPPORTED_INTEGRATIONS = (
    "claude_code",
    "cursor",
    "git",
    "generic",
    "mcp",
    "aider",
    "openhands",
    "windsurf",
    "continue",
)

_TESTED_VERSIONS = {
    "claude_code": "Claude Code >=1.0 (Stop hook spec)",
    "cursor": "Cursor >=0.45 (.cursor/rules/*.mdc)",
    "git": "Git >=2.30 (pre-commit hook)",
    "generic": f"DoneGate v{__version__}",
    "mcp": "MCP 2024-11-05 (JSON-RPC 2.0 stdio)",
    "aider": "Aider >=0.50 (.aider.conf.yml)",
    "openhands": "OpenHands >=0.14 (.openhands/microagents)",
    "windsurf": "Windsurf >=1.0 (.windsurfrules)",
    "continue": "Continue.dev >=1.0 (.continue/rules)",
}


class IntegrationResult(BaseModel):
    """Result of generating integration files."""

    name: str
    tested_against: str
    files_written: list[str] = Field(default_factory=list)
    notes: str = ""


def _integrate_claude_code(repo_root: Path) -> IntegrationResult:
    claude_md = repo_root / "CLAUDE.md"
    snippet = (
        "<!-- donegate:start -->\n"
        f"## DoneGate Contract Enforcement (tested against {_TESTED_VERSIONS['claude_code']})\n"
        "- Before claiming any task is done, run `donegate next` and `donegate start <id>`.\n"
        "- Only edit files inside the task's `scope.allow` globs.\n"
        "- Run `donegate check <id>` and verify exit code 0 before stopping.\n"
        "<!-- donegate:end -->\n"
    )
    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if "<!-- donegate:start -->" not in existing:
            atomic_write_text(claude_md, existing.rstrip() + "\n\n" + snippet)
    else:
        atomic_write_text(claude_md, snippet)

    settings_path = repo_root / ".claude" / "settings.json"
    settings: dict[str, object] = {}
    if settings_path.is_file():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings = loaded
        except json.JSONDecodeError:
            settings = {}

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    hooks["Stop"] = [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": "donegate check --all",
                }
            ],
        }
    ]
    settings["hooks"] = hooks
    settings["x-donegate-tested-against"] = _TESTED_VERSIONS["claude_code"]
    atomic_write_text(settings_path, json.dumps(settings, indent=2) + "\n")

    return IntegrationResult(
        name="claude_code",
        tested_against=_TESTED_VERSIONS["claude_code"],
        files_written=["CLAUDE.md", ".claude/settings.json"],
        notes="Configured CLAUDE.md instructions and Claude Code Stop hook.",
    )


def _integrate_cursor(repo_root: Path) -> IntegrationResult:
    rule_path = repo_root / ".cursor" / "rules" / "donegate.mdc"
    content = (
        "---\n"
        "description: Enforce DoneGate task contracts, scope, and checks\n"
        "alwaysApply: true\n"
        "---\n\n"
        f"# DoneGate Rules (tested against {_TESTED_VERSIONS['cursor']})\n\n"
        "1. Run `donegate next` to pick your active task and `donegate start <id>`.\n"
        "2. Do not modify files outside the task's `scope.allow` patterns.\n"
        "3. Never declare a task complete until `donegate check <id>` exits 0.\n"
    )
    atomic_write_text(rule_path, content)
    return IntegrationResult(
        name="cursor",
        tested_against=_TESTED_VERSIONS["cursor"],
        files_written=[".cursor/rules/donegate.mdc"],
        notes="Created Cursor always-apply rule file.",
    )


def _integrate_git(repo_root: Path) -> IntegrationResult:
    hook_path = repo_root / ".git" / "hooks" / "pre-commit"
    script = (
        "#!/usr/bin/env sh\n"
        f"# DoneGate pre-commit scope guard (tested against {_TESTED_VERSIONS['git']})\n"
        "set -e\n"
        "if [ -f done.yaml ]; then\n"
        "  donegate check --all\n"
        "fi\n"
    )
    atomic_write_text(hook_path, script)
    if os.name != "nt":
        mode = hook_path.stat().st_mode
        hook_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return IntegrationResult(
        name="git",
        tested_against=_TESTED_VERSIONS["git"],
        files_written=[".git/hooks/pre-commit"],
        notes="Installed git pre-commit hook running DoneGate check on active tasks.",
    )


def _integrate_generic(repo_root: Path) -> IntegrationResult:
    prompt_path = repo_root / "DONEGATE_PROMPT.md"
    content = (
        f"# DoneGate Agent System Prompt (tested against {_TESTED_VERSIONS['generic']})\n\n"
        "You are operating under a DoneGate contract (`done.yaml`).\n"
        "Follow this exact loop for every task:\n"
        "1. Run `donegate next --json` to find the highest-priority runnable task.\n"
        "2. Run `donegate start <task-id>` to snapshot the git baseline and start the timer.\n"
        "3. Edit ONLY files matching the task's `scope.allow` globs (avoid `scope.deny`).\n"
        "4. Run `donegate check <task-id>`. If it fails, read the <=15-line summary and fix.\n"
        "5. Never say 'done' until `donegate check <task-id>` exits with code 0.\n"
    )
    atomic_write_text(prompt_path, content)
    return IntegrationResult(
        name="generic",
        tested_against=_TESTED_VERSIONS["generic"],
        files_written=["DONEGATE_PROMPT.md"],
        notes="Generated copy-paste system prompt for any AI agent.",
    )


def _integrate_mcp(repo_root: Path) -> IntegrationResult:
    mcp_config = repo_root / ".mcp.json"
    config = {
        "x-donegate-tested-against": _TESTED_VERSIONS["mcp"],
        "mcpServers": {
            "donegate": {
                "command": "python",
                "args": ["-m", "donegate.integrations.mcp_server", "--repo", "."],
            }
        },
    }
    atomic_write_text(mcp_config, json.dumps(config, indent=2) + "\n")
    return IntegrationResult(
        name="mcp",
        tested_against=_TESTED_VERSIONS["mcp"],
        files_written=[".mcp.json"],
        notes="Configured stdio MCP server exposing donegate_next/start/check/status.",
    )


def _integrate_aider(repo_root: Path) -> IntegrationResult:
    prompt_path = repo_root / "DONEGATE_AIDER.md"
    atomic_write_text(
        prompt_path,
        f"# DoneGate Aider Instructions ({_TESTED_VERSIONS['aider']})\n\n"
        "- Run `donegate next --json` and `donegate start <id>` before editing.\n"
        "- Stay within `scope.allow` globs.\n"
        "- Run `donegate check <id>` before finishing.\n",
    )
    conf_path = repo_root / ".aider.conf.yml"
    atomic_write_text(
        conf_path,
        "# DoneGate Aider configuration\n"
        "read: DONEGATE_AIDER.md\n"
        "test-cmd: donegate check\n"
        "auto-test: false\n",
    )
    return IntegrationResult(
        name="aider",
        tested_against=_TESTED_VERSIONS["aider"],
        files_written=[".aider.conf.yml", "DONEGATE_AIDER.md"],
        notes="Configured Aider conventions and DONEGATE_AIDER.md.",
    )


def _integrate_openhands(repo_root: Path) -> IntegrationResult:
    micro_path = repo_root / ".openhands" / "microagents" / "donegate.md"
    atomic_write_text(
        micro_path,
        "---\n"
        "name: donegate\n"
        "type: repo\n"
        "---\n\n"
        f"# DoneGate Microagent ({_TESTED_VERSIONS['openhands']})\n\n"
        "Always run `donegate start <id>` before editing and `donegate check <id>` "
        "before declaring completion.\n",
    )
    return IntegrationResult(
        name="openhands",
        tested_against=_TESTED_VERSIONS["openhands"],
        files_written=[".openhands/microagents/donegate.md"],
        notes="Created OpenHands repository microagent.",
    )


def _integrate_windsurf(repo_root: Path) -> IntegrationResult:
    rules_path = repo_root / ".windsurfrules"
    atomic_write_text(
        rules_path,
        f"# DoneGate Rules ({_TESTED_VERSIONS['windsurf']})\n\n"
        "1. Run `donegate next` and `donegate start <id>`.\n"
        "2. Edit only files allowed by the active task's `scope.allow`.\n"
        "3. Do not say 'done' until `donegate check <id>` exits 0.\n",
    )
    return IntegrationResult(
        name="windsurf",
        tested_against=_TESTED_VERSIONS["windsurf"],
        files_written=[".windsurfrules"],
        notes="Created .windsurfrules for Windsurf.",
    )


def _integrate_continue(repo_root: Path) -> IntegrationResult:
    rule_path = repo_root / ".continue" / "rules" / "donegate.md"
    atomic_write_text(
        rule_path,
        f"# DoneGate Rules ({_TESTED_VERSIONS['continue']})\n\n"
        "- Use `donegate next`, `donegate start <id>`, and `donegate check <id>`.\n"
        "- Never touch files outside `scope.allow`.\n",
    )
    return IntegrationResult(
        name="continue",
        tested_against=_TESTED_VERSIONS["continue"],
        files_written=[".continue/rules/donegate.md"],
        notes="Created Continue.dev rule file.",
    )


def apply_integration(repo_root: Path, name: str) -> IntegrationResult:
    """Generate integration files for the requested tool."""
    handlers = {
        "claude_code": _integrate_claude_code,
        "cursor": _integrate_cursor,
        "git": _integrate_git,
        "generic": _integrate_generic,
        "mcp": _integrate_mcp,
        "aider": _integrate_aider,
        "openhands": _integrate_openhands,
        "windsurf": _integrate_windsurf,
        "continue": _integrate_continue,
    }
    key = name.lower()
    if key in handlers:
        return handlers[key](repo_root)
    raise KeyError(
        f"Unknown integration {name!r}. Supported: {', '.join(SUPPORTED_INTEGRATIONS)}"
    )
