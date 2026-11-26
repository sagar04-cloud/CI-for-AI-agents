"""Supervisor orchestration: next, start, check, usage/budget, on_fail, deadline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from donegate.checks.base import CheckContext, CheckResult, format_failure_summary, run_checks
from donegate.contract.loader import load_contract
from donegate.contract.models import (
    Contract,
    OnFailStrategy,
    ScopeMode,
    TaskSpec,
    TaskStatus,
)
from donegate.scope.guard import ScopeCheckResult, check_scope, snapshot_baseline
from donegate.supervisor.state import (
    EventRecord,
    RunState,
    TaskRuntimeState,
    append_event,
    load_state,
    read_events,
    save_state,
    utc_now,
)


class CheckOutcome(BaseModel):
    """Combined result of running checks, scope guard, and budget checks on a task."""

    task_id: str
    passed: bool
    status: TaskStatus
    summary: str
    check_results: list[CheckResult] = Field(default_factory=list)
    scope_result: ScopeCheckResult | None = None
    budget_exceeded: bool = False
    deadline_warning: str | None = None


class Supervisor:
    """Stateful supervisor enforcing a DoneGate contract on a repository."""

    def __init__(self, repo_root: Path, contract_path: Path | str = "done.yaml") -> None:
        self.repo_root = repo_root.resolve()
        cpath = Path(contract_path)
        self.contract_path = cpath if cpath.is_absolute() else (self.repo_root / cpath)
        self.contract: Contract = load_contract(self.contract_path)
        self.state = self._load_or_init_state()

    def _load_or_init_state(self) -> RunState:
        existing = load_state(self.repo_root)
        if existing is not None:
            for task in self.contract.tasks:
                if task.id not in existing.tasks:
                    existing.tasks[task.id] = TaskRuntimeState(
                        status=task.status, usage=task.usage
                    )
            return existing

        tasks_state = {
            task.id: TaskRuntimeState(status=task.status, usage=task.usage)
            for task in self.contract.tasks
        }
        state = RunState(
            contract_path=str(self.contract_path.relative_to(self.repo_root))
            if self.contract_path.is_relative_to(self.repo_root)
            else str(self.contract_path),
            goal=self.contract.goal,
            tasks=tasks_state,
        )
        save_state(self.repo_root, state)
        return state

    def _active_profile_names(self) -> list[str] | None:
        if isinstance(self.contract.language_profile, str):
            return [self.contract.language_profile]
        if isinstance(self.contract.language_profile, list):
            return list(self.contract.language_profile)
        if self.contract.profiles:
            return [p.profile for p in self.contract.profiles]
        return None

    def _check_deadline_risk(self) -> str | None:
        dl = self.contract.deadline
        if dl is None:
            return None
        if isinstance(dl, str):
            try:
                dl_dt = datetime.fromisoformat(dl.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            dl_dt = dl
        if dl_dt.tzinfo is None:
            dl_dt = dl_dt.replace(tzinfo=timezone.utc)
        remaining = (dl_dt - utc_now()).total_seconds()
        if remaining <= 0:
            return "DEADLINE EXCEEDED: contract deadline has passed."
        if remaining <= 3600:
            mins = max(1, int(remaining // 60))
            return f"DEADLINE RISK: only {mins} minute(s) remaining until deadline."
        return None

    def _budget_error(self, task: TaskSpec, rt: TaskRuntimeState) -> str | None:
        b = task.budget
        if b.steps is not None and rt.usage.steps > b.steps:
            return f"Budget overrun: steps {rt.usage.steps} > limit {b.steps}"
        if b.minutes is not None and rt.usage.minutes > b.minutes:
            return f"Budget overrun: minutes {rt.usage.minutes:.2f} > limit {b.minutes}"
        if b.tokens is not None and rt.usage.tokens > b.tokens:
            return f"Budget overrun: tokens {rt.usage.tokens} > limit {b.tokens}"
        return None

    def next_tasks(self) -> list[TaskSpec]:
        """Return runnable tasks (pending with satisfied deps), sorted by priority desc."""
        runnable: list[TaskSpec] = []
        for task in self.contract.tasks:
            rt = self.state.tasks[task.id]
            if rt.status != TaskStatus.PENDING:
                continue
            deps_ok = all(
                self.state.tasks[dep].status in (TaskStatus.DONE, TaskStatus.SKIPPED)
                for dep in task.depends_on
            )
            if deps_ok:
                runnable.append(task)
        return sorted(runnable, key=lambda t: t.priority, reverse=True)

    def start(self, task_id: str) -> TaskRuntimeState:
        """Start a task: verify deps, snapshot git baseline, start timer."""
        task = self.contract.get_task(task_id)
        rt = self.state.tasks[task_id]
        unmet = [
            dep
            for dep in task.depends_on
            if self.state.tasks[dep].status not in (TaskStatus.DONE, TaskStatus.SKIPPED)
        ]
        if unmet:
            raise RuntimeError(f"Task {task_id!r} blocked on dependencies: {', '.join(unmet)}")

        rt.status = TaskStatus.IN_PROGRESS
        rt.started_at = utc_now()
        rt.baseline = snapshot_baseline(self.repo_root)
        save_state(self.repo_root, self.state)
        append_event(
            self.repo_root,
            EventRecord(
                event="task_started",
                task_id=task_id,
                status=rt.status.value,
                details={"head_sha": rt.baseline.head_sha},
            ),
        )
        return rt

    def report_usage(
        self, task_id: str, steps: int = 0, minutes: float = 0.0, tokens: int = 0
    ) -> tuple[TaskRuntimeState, str | None]:
        """Record agent resource usage and detect budget overruns."""
        task = self.contract.get_task(task_id)
        rt = self.state.tasks[task_id]
        rt.usage.steps += steps
        rt.usage.minutes += minutes
        rt.usage.tokens += tokens

        overrun = self._budget_error(task, rt)
        if overrun:
            rt.status = TaskStatus.FAILED
            rt.last_summary = overrun
        save_state(self.repo_root, self.state)
        append_event(
            self.repo_root,
            EventRecord(
                event="usage_reported",
                task_id=task_id,
                status=rt.status.value,
                details={
                    "usage": rt.usage.model_dump(),
                    "budget_overrun": overrun,
                },
            ),
        )
        return rt, overrun

    def approve(self, task_id: str) -> TaskRuntimeState:
        """Grant human approval for a task."""
        self.contract.get_task(task_id)
        rt = self.state.tasks[task_id]
        rt.human_approved = True
        save_state(self.repo_root, self.state)
        append_event(
            self.repo_root,
            EventRecord(event="human_approved", task_id=task_id, status=rt.status.value),
        )
        return rt

    def check(
        self,
        task_id: str,
        scope_mode: ScopeMode | None = None,
        approve: bool = False,
    ) -> CheckOutcome:
        """Run budget, human-approval, scope guard, and task checks; update state & log."""
        task = self.contract.get_task(task_id)
        rt = self.state.tasks[task_id]
        if approve:
            rt.human_approved = True

        rt.usage.steps += 1
        if rt.started_at is not None:
            elapsed_min = max(0.0, (utc_now() - rt.started_at).total_seconds() / 60.0)
            rt.usage.minutes = max(rt.usage.minutes, round(elapsed_min, 4))

        deadline_warning = self._check_deadline_risk()
        overrun = self._budget_error(task, rt)
        if overrun:
            rt.status = TaskStatus.FAILED
            rt.last_summary = overrun
            save_state(self.repo_root, self.state)
            append_event(
                self.repo_root,
                EventRecord(
                    event="budget_overrun",
                    task_id=task_id,
                    status=rt.status.value,
                    details={"reason": overrun, "deadline_warning": deadline_warning},
                ),
            )
            return CheckOutcome(
                task_id=task_id,
                passed=False,
                status=rt.status,
                summary=overrun,
                budget_exceeded=True,
                deadline_warning=deadline_warning,
            )

        mode = scope_mode or self.contract.scope_mode
        scope_res = check_scope(
            self.repo_root,
            task.scope,
            mode=mode,
            baseline=rt.baseline,
            active_profiles=self._active_profile_names(),
        )

        approvals = {task_id} if rt.human_approved else set()
        ctx = CheckContext(
            repo_root=self.repo_root,
            task_id=task_id,
            criticality=task.criticality,
            human_approvals=approvals,
        )
        check_results = run_checks(task, ctx)

        if task.needs_human_approval and not rt.human_approved:
            check_results.append(
                CheckResult(
                    passed=False,
                    message="Task requires human approval before completion",
                    check_name="needs_human_approval",
                    check_type="human_approval",
                    suggested_action=f"Approve with `donegate check {task_id} --approve`.",
                )
            )

        all_results = list(check_results)
        if not scope_res.passed:
            all_results.append(
                CheckResult(
                    passed=False,
                    message=scope_res.message,
                    check_name="scope_guard",
                    check_type="scope_guard",
                    evidence={"key_error_lines": scope_res.revert_commands[:4]},
                    suggested_action="Revert out-of-scope files or update task scope.",
                )
            )

        all_passed = all(r.passed for r in all_results)
        if all_passed:
            rt.status = TaskStatus.DONE
            rt.finished_at = utc_now()
            rt.last_summary = f"Task {task_id} passed all checks."
            save_state(self.repo_root, self.state)
            append_event(
                self.repo_root,
                EventRecord(
                    event="task_passed",
                    task_id=task_id,
                    status=rt.status.value,
                    details={
                        "usage": rt.usage.model_dump(),
                        "deadline_warning": deadline_warning,
                    },
                ),
            )
            return CheckOutcome(
                task_id=task_id,
                passed=True,
                status=rt.status,
                summary=rt.last_summary,
                check_results=check_results,
                scope_result=scope_res,
                deadline_warning=deadline_warning,
            )

        summary = format_failure_summary(all_results, max_lines=15)
        rt.usage.retries += 1
        strategy = task.on_fail.strategy

        if task.needs_human_approval and not rt.human_approved and all(
            r.passed for r in all_results if r.check_type != "human_approval"
        ):
            rt.status = TaskStatus.AWAITING_HUMAN
        elif strategy == OnFailStrategy.SKIP_AND_FLAG:
            rt.status = TaskStatus.SKIPPED
            rt.flagged_reason = summary
        elif strategy == OnFailStrategy.ASK_HUMAN:
            rt.status = TaskStatus.AWAITING_HUMAN
        elif rt.usage.retries > task.on_fail.max_retries:
            rt.status = TaskStatus.FAILED
        else:
            rt.status = TaskStatus.IN_PROGRESS

        rt.last_summary = summary
        save_state(self.repo_root, self.state)
        append_event(
            self.repo_root,
            EventRecord(
                event="task_failed",
                task_id=task_id,
                status=rt.status.value,
                details={
                    "retries": rt.usage.retries,
                    "strategy": strategy.value,
                    "scope_violations": scope_res.out_of_scope_files,
                    "deadline_warning": deadline_warning,
                },
            ),
        )
        return CheckOutcome(
            task_id=task_id,
            passed=False,
            status=rt.status,
            summary=summary,
            check_results=check_results,
            scope_result=scope_res,
            deadline_warning=deadline_warning,
        )

    def reset_task(self, task_id: str | None = None) -> list[str]:
        """Reset one task (or all tasks if task_id is None) back to pending."""
        targets = [task_id] if task_id is not None else [t.id for t in self.contract.tasks]
        for tid in targets:
            self.contract.get_task(tid)
            self.state.tasks[tid] = TaskRuntimeState(status=TaskStatus.PENDING)
            append_event(
                self.repo_root,
                EventRecord(event="task_reset", task_id=tid, status=TaskStatus.PENDING.value),
            )
        save_state(self.repo_root, self.state)
        return targets

    def check_all_in_progress(self, scope_mode: ScopeMode | None = None) -> list[CheckOutcome]:
        """Run check() on every task currently in_progress."""
        outcomes: list[CheckOutcome] = []
        for task in self.contract.tasks:
            if self.state.tasks[task.id].status == TaskStatus.IN_PROGRESS:
                outcomes.append(self.check(task.id, scope_mode=scope_mode))
        return outcomes

    def build_report(self) -> dict[str, Any]:
        """Aggregate usage, cost, retries, and scope violations from state and events.log."""
        events = read_events(self.repo_root)
        scope_violations = 0
        for ev in events:
            if ev.event == "task_failed" and ev.details.get("scope_violations"):
                scope_violations += len(ev.details["scope_violations"])

        task_rows: list[dict[str, Any]] = []
        total_steps = 0
        total_tokens = 0
        total_retries = 0
        total_minutes = 0.0
        done_count = 0
        for task in self.contract.tasks:
            rt = self.state.tasks[task.id]
            total_steps += rt.usage.steps
            total_tokens += rt.usage.tokens
            total_retries += rt.usage.retries
            total_minutes += rt.usage.minutes
            if rt.status == TaskStatus.DONE:
                done_count += 1
            task_rows.append(
                {
                    "id": task.id,
                    "status": rt.status.value,
                    "steps": rt.usage.steps,
                    "retries": rt.usage.retries,
                    "tokens": rt.usage.tokens,
                    "minutes": round(rt.usage.minutes, 3),
                }
            )
        return {
            "goal": self.contract.goal,
            "total_tasks": len(self.contract.tasks),
            "done_tasks": done_count,
            "total_steps": total_steps,
            "total_retries": total_retries,
            "total_tokens": total_tokens,
            "total_minutes": round(total_minutes, 3),
            "scope_violations": scope_violations,
            "events_count": len(events),
            "tasks": task_rows,
        }
