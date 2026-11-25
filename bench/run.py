"""DoneBench runner: compares baseline (no gate) vs DoneGate across all tasks."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from bench.mock_agent import run_mock_agent
from bench.tasks import TASKS, BenchTask
from donegate.supervisor import Supervisor


class TaskRunMetrics(BaseModel):
    """Metrics recorded for one task in one mode."""

    task_id: str
    language: str
    mode: str  # "baseline" | "donegate"
    truly_passed: bool
    agent_claimed_done: bool
    false_done: bool
    out_of_scope_edits: int
    steps: int
    tokens: int
    seconds: float


def _init_task_repo(root: Path, task: BenchTask) -> None:
    subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "bench@donegate.dev"],
        cwd=str(root),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "DoneBench"],
        cwd=str(root),
        check=True,
        capture_output=True,
    )
    for rel, content in task.files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    (root / "done.yaml").write_text(task.done_yaml, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(root), check=True, capture_output=True)


def _run_external_agent(cmd: str, repo: Path, task: BenchTask, feedback: str) -> tuple[bool, int]:
    env_cmd = cmd.format(task_id=task.id, repo=str(repo))
    proc = subprocess.run(
        env_cmd,
        shell=True,
        cwd=str(repo),
        input=feedback,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode == 0, 1000


def run_task(task: BenchTask, agent: str, with_gate: bool) -> TaskRunMetrics:
    """Execute one task in either baseline or DoneGate mode."""
    with tempfile.TemporaryDirectory(prefix=f"donebench-{task.id}-") as tmp:
        repo = Path(tmp)
        _init_task_repo(repo, task)
        started = time.monotonic()

        total_tokens = 0
        steps = 0
        claimed_done = False
        out_of_scope = 0

        if not with_gate:
            steps = 1
            if agent == "mock":
                claimed_done, tok = run_mock_agent(repo, task, attempt=1, with_gate=False)
            else:
                claimed_done, tok = _run_external_agent(agent, repo, task, "")
            total_tokens += tok
            sup = Supervisor(repo)
            sup.start(task.id)
            outcome = sup.check(task.id)
            out_of_scope = (
                len(outcome.scope_result.out_of_scope_files) if outcome.scope_result else 0
            )
        else:
            sup = Supervisor(repo)
            sup.start(task.id)
            feedback = ""
            for attempt in range(1, 4):
                steps += 1
                if agent == "mock":
                    claimed_done, tok = run_mock_agent(
                        repo, task, attempt=attempt, with_gate=True, feedback=feedback
                    )
                else:
                    claimed_done, tok = _run_external_agent(agent, repo, task, feedback)
                total_tokens += tok
                sup.report_usage(task.id, tokens=tok)
                outcome = sup.check(task.id)
                if outcome.scope_result:
                    out_of_scope = max(out_of_scope, len(outcome.scope_result.out_of_scope_files))
                if outcome.passed:
                    break
                feedback = outcome.summary

        truly_passed = task.hidden_verifier(repo)
        elapsed = round(time.monotonic() - started, 3)
        return TaskRunMetrics(
            task_id=task.id,
            language=task.language,
            mode="donegate" if with_gate else "baseline",
            truly_passed=truly_passed,
            agent_claimed_done=claimed_done,
            false_done=claimed_done and not truly_passed,
            out_of_scope_edits=out_of_scope,
            steps=steps,
            tokens=total_tokens,
            seconds=elapsed,
        )


def render_markdown(metrics: list[TaskRunMetrics], agent: str) -> str:
    """Render DoneBench results.md with overall table, per-language table, and limits."""
    by_mode: dict[str, list[TaskRunMetrics]] = defaultdict(list)
    for m in metrics:
        by_mode[m.mode].append(m)

    lines = [
        "# DoneBench Results",
        "",
        f"Agent: `{agent}` | Tasks: {len(TASKS)} across 4 languages (Python, TypeScript, Go, Rust)",
        "",
        "## Overall Summary",
        "",
        (
            "| Mode | Tasks | Truly Passed | False-Done Rate | "
            "Out-of-Scope Edits | Total Tokens | Total Time (s) |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in ("baseline", "donegate"):
        rows = by_mode[mode]
        n = len(rows)
        passed = sum(1 for r in rows if r.truly_passed)
        false_done = sum(1 for r in rows if r.false_done)
        oos = sum(r.out_of_scope_edits for r in rows)
        toks = sum(r.tokens for r in rows)
        secs = round(sum(r.seconds for r in rows), 2)
        pct = f"{(false_done / n * 100):.1f}%" if n else "0.0%"
        row = f"| {mode} | {n} | {passed}/{n} | {pct} ({false_done}) | {oos} | {toks} | {secs} |"
        lines.append(row)

    lines.extend(
        [
            "",
            "## Per-Language Breakdown",
            "",
            "| Language | Mode | Passed | False-Done | Out-of-Scope |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    langs = sorted({m.language for m in metrics})
    for lang in langs:
        for mode in ("baseline", "donegate"):
            sub = [m for m in metrics if m.language == lang and m.mode == mode]
            passed = sum(1 for r in sub if r.truly_passed)
            fd = sum(1 for r in sub if r.false_done)
            oos = sum(r.out_of_scope_edits for r in sub)
            lines.append(f"| {lang} | {mode} | {passed}/{len(sub)} | {fd} | {oos} |")

    lines.extend(
        [
            "",
            "## Method & Honest Limitations",
            "",
            "- Each task initializes a fresh temporary git repo with a hidden verifier.",
            "- Every task runs twice: once without DoneGate (`baseline`) and once with DoneGate.",
            (
                "- The `mock` agent deterministically simulates premature 'done' claims and "
                "out-of-scope edits to exercise the harness offline."
            ),
            (
                "- Real-world LLM agents vary by model, prompt, and repo complexity; "
                "run `--agent \"<cmd>\"` to benchmark live agents."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def run_benchmark(
    agent: str = "mock", output_path: Path = Path("bench/results.md")
) -> list[TaskRunMetrics]:
    """Run all DoneBench tasks in both modes and write results.md."""
    metrics: list[TaskRunMetrics] = []
    for task in TASKS:
        metrics.append(run_task(task, agent=agent, with_gate=False))
        metrics.append(run_task(task, agent=agent, with_gate=True))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(metrics, agent=agent), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DoneBench")
    parser.add_argument("--agent", default="mock", help="Agent mode ('mock' or shell command)")
    parser.add_argument("--out", default="bench/results.md", help="Output Markdown path")
    ns = parser.parse_args()
    metrics = run_benchmark(agent=ns.agent, output_path=Path(ns.out))
    print(f"DoneBench completed {len(metrics)} runs -> {ns.out}")


if __name__ == "__main__":
    main()
