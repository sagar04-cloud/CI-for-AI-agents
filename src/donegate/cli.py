"""Typer + Rich CLI for DoneGate."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from donegate import __version__
from donegate.contract import (
    ContractValidationError,
    ScopeMode,
    dump_contract,
    export_contract_schema,
    load_contract,
)
from donegate.integrations import SUPPORTED_INTEGRATIONS, apply_integration
from donegate.profiles import detect_profiles, generate_contract
from donegate.supervisor import Supervisor, read_events

app = typer.Typer(
    name="donegate",
    help="CI for AI agents: executable contracts, scope guards, budgets, and checks.",
    no_args_is_help=True,
)
console = Console()
ContractFileOpt = Annotated[Path, typer.Option("--file", "-f", help="Contract file path")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Emit JSON output")]


def _emit_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


@app.command()
def version() -> None:
    """Show DoneGate version."""
    typer.echo(f"donegate {__version__}")


@app.command()
def init(
    template: str | None = typer.Option(None, "--template", "-t", help="Language profile name"),
    goal: str = typer.Option(
        "Complete task safely within DoneGate contract", "--goal", "-g", help="Contract goal"
    ),
    file: ContractFileOpt = Path("done.yaml"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing done.yaml"),
    json_output: JsonOpt = False,
) -> None:
    """Auto-detect project language(s) and generate done.yaml."""
    repo_root = Path.cwd()
    target = file if file.is_absolute() else (repo_root / file)
    if target.exists() and not force:
        msg = f"{file} already exists (use --force to overwrite)"
        if json_output:
            _emit_json({"ok": False, "error": msg})
        else:
            console.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    try:
        contract = generate_contract(repo_root, goal=goal, template_profile=template)
    except KeyError as exc:
        if json_output:
            _emit_json({"ok": False, "error": str(exc)})
        else:
            console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    dump_contract(contract, target)
    if json_output:
        _emit_json(
            {
                "ok": True,
                "path": str(target),
                "language_profile": contract.language_profile,
                "tasks": [t.id for t in contract.tasks],
            }
        )
    else:
        console.print(
            f"[green]Created[/green] {file} "
            f"(profile={contract.language_profile}, tasks={len(contract.tasks)})"
        )


@app.command()
def validate(
    file: ContractFileOpt = Path("done.yaml"),
    json_output: JsonOpt = False,
) -> None:
    """Validate a done.yaml contract."""
    try:
        contract = load_contract(file)
    except ContractValidationError as exc:
        if json_output:
            _emit_json({"valid": False, "errors": exc.errors})
        else:
            console.print(f"[red]Invalid contract:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        _emit_json({"valid": True, "goal": contract.goal, "task_count": len(contract.tasks)})
    else:
        console.print(f"[green]Valid[/green] contract: {len(contract.tasks)} task(s)")


@app.command()
def next(
    file: ContractFileOpt = Path("done.yaml"),
    json_output: JsonOpt = False,
) -> None:
    """List runnable tasks ordered by priority."""
    sup = Supervisor(Path.cwd(), file)
    tasks = sup.next_tasks()
    if json_output:
        _emit_json([t.model_dump(mode="json") for t in tasks])
        return

    if not tasks:
        console.print("[yellow]No runnable tasks available.[/yellow]")
        return
    table = Table(title="Runnable Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Priority", justify="right")
    table.add_column("Title")
    for t in tasks:
        table.add_row(t.id, str(t.priority), t.title)
    console.print(table)


@app.command()
def start(
    task_id: str = typer.Argument(..., help="Task ID to start"),
    file: ContractFileOpt = Path("done.yaml"),
    json_output: JsonOpt = False,
) -> None:
    """Start a task: snapshot git baseline and begin timer."""
    sup = Supervisor(Path.cwd(), file)
    try:
        rt = sup.start(task_id)
    except (KeyError, RuntimeError) as exc:
        if json_output:
            _emit_json({"ok": False, "error": str(exc)})
        else:
            console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        _emit_json({"ok": True, "task_id": task_id, "state": rt.model_dump(mode="json")})
    else:
        console.print(f"[green]Started[/green] task [bold]{task_id}[/bold]")


@app.command()
def check(
    task_id: str = typer.Argument(..., help="Task ID to check"),
    file: ContractFileOpt = Path("done.yaml"),
    mode: Annotated[
        ScopeMode | None, typer.Option("--mode", help="Override scope guard mode")
    ] = None,
    approve: bool = typer.Option(False, "--approve", help="Grant human approval for this task"),
    json_output: JsonOpt = False,
) -> None:
    """Run checks, scope guard, and budget enforcement for a task."""
    sup = Supervisor(Path.cwd(), file)
    try:
        outcome = sup.check(task_id, scope_mode=mode, approve=approve)
    except KeyError as exc:
        if json_output:
            _emit_json({"ok": False, "error": str(exc)})
        else:
            console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        _emit_json(outcome.model_dump(mode="json"))
    else:
        color = "green" if outcome.passed else "red"
        console.print(f"[{color}]{outcome.summary}[/{color}]")
        if outcome.deadline_warning:
            console.print(f"[yellow]{outcome.deadline_warning}[/yellow]")

    if not outcome.passed:
        raise typer.Exit(code=1)


@app.command("report-usage")
def report_usage_cmd(
    task_id: str = typer.Argument(..., help="Task ID"),
    steps: int = typer.Option(0, "--steps", help="Steps to add"),
    minutes: float = typer.Option(0.0, "--minutes", help="Minutes to add"),
    tokens: int = typer.Option(0, "--tokens", help="Tokens to add"),
    file: ContractFileOpt = Path("done.yaml"),
    json_output: JsonOpt = False,
) -> None:
    """Report agent step/time/token usage for a task."""
    sup = Supervisor(Path.cwd(), file)
    rt, overrun = sup.report_usage(task_id, steps=steps, minutes=minutes, tokens=tokens)
    if json_output:
        _emit_json({"task_id": task_id, "usage": rt.usage.model_dump(), "overrun": overrun})
    else:
        console.print(f"Updated usage for {task_id}: {rt.usage.model_dump()}")
        if overrun:
            console.print(f"[red]{overrun}[/red]")
    if overrun:
        raise typer.Exit(code=1)


@app.command()
def status(
    file: ContractFileOpt = Path("done.yaml"),
    json_output: JsonOpt = False,
) -> None:
    """Show overall contract and task status."""
    sup = Supervisor(Path.cwd(), file)
    if json_output:
        _emit_json(sup.state.model_dump(mode="json"))
        return

    table = Table(title=f"DoneGate Status: {sup.contract.goal}")
    table.add_column("Task ID", style="cyan")
    table.add_column("Status")
    table.add_column("Steps", justify="right")
    table.add_column("Retries", justify="right")
    table.add_column("Tokens", justify="right")
    for task in sup.contract.tasks:
        rt = sup.state.tasks[task.id]
        table.add_row(
            task.id,
            rt.status.value,
            str(rt.usage.steps),
            str(rt.usage.retries),
            str(rt.usage.tokens),
        )
    console.print(table)


@app.command()
def log(
    limit: int = typer.Option(50, "--limit", "-n", help="Max recent events"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Inspect .donegate/events.log replay history."""
    events = read_events(Path.cwd())[-limit:]
    if json_output:
        _emit_json([e.model_dump(mode="json") for e in events])
        return

    if not events:
        console.print("No events logged yet.")
        return
    for ev in events:
        ts = ev.timestamp.isoformat()
        console.print(f"{ts} | {ev.event} | {ev.task_id or '-'} | {ev.status}")


@app.command()
def export(
    schema: bool = typer.Option(False, "--schema", help="Export contract JSON Schema"),
    file: ContractFileOpt = Path("done.yaml"),
    json_output: JsonOpt = False,
) -> None:
    """Export versioned JSON Schema or contract summary."""
    if schema:
        _emit_json(export_contract_schema())
        return
    contract = load_contract(file)
    if json_output:
        _emit_json(contract.to_yaml_dict())
    else:
        _emit_json(contract.to_yaml_dict())


@app.command()
def integrate(
    name: str = typer.Argument(..., help=f"One of: {', '.join(SUPPORTED_INTEGRATIONS)}"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Generate integration files for an agent or git hook."""
    try:
        res = apply_integration(Path.cwd(), name)
    except KeyError as exc:
        if json_output:
            _emit_json({"ok": False, "error": str(exc)})
        else:
            console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        _emit_json(res.model_dump(mode="json"))
    else:
        console.print(
            f"[green]Integrated {res.name}[/green] ({res.tested_against}): "
            f"{', '.join(res.files_written)}"
        )


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Verify git, Python, detected languages, and required toolchain binaries."""
    repo_root = Path.cwd()
    git_ok = shutil.which("git") is not None
    git_ver = ""
    if git_ok:
        proc = subprocess.run(["git", "--version"], capture_output=True, text=True)
        git_ver = proc.stdout.strip()

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)

    detected = detect_profiles(repo_root)
    tool_checks: list[dict[str, Any]] = []
    all_tools_ok = True
    for item in detected:
        for tool in item.profile.tool_binaries:
            found = shutil.which(tool) is not None
            if not found:
                all_tools_ok = False
            tool_checks.append(
                {
                    "profile": item.profile.name,
                    "path": item.rel_path,
                    "tool": tool,
                    "available": found,
                    "hint": "" if found else f"Install '{tool}' and ensure it is on PATH.",
                }
            )

    report = {
        "ok": git_ok and py_ok and all_tools_ok,
        "python": {"version": py_ver, "ok": py_ok},
        "git": {"available": git_ok, "version": git_ver},
        "detected_profiles": [{"profile": d.profile.name, "path": d.rel_path} for d in detected],
        "tools": tool_checks,
    }
    if json_output:
        _emit_json(report)
        return

    console.print(f"Python: {py_ver} ({'ok' if py_ok else 'upgrade to >=3.10'})")
    console.print(f"Git: {git_ver or 'NOT FOUND'}")
    if detected:
        console.print(
            "Detected profiles: " + ", ".join(f"{d.profile.name} ({d.rel_path})" for d in detected)
        )
    else:
        console.print("Detected profiles: none")
    for tc in tool_checks:
        ok_str = "[green]ok[/green]"
        miss_str = f"[red]missing[/red] ({tc['hint']})"
        status_str = ok_str if tc["available"] else miss_str
        console.print(f"  - [{tc['profile']}] {tc['tool']}: {status_str}")


if __name__ == "__main__":
    app()
