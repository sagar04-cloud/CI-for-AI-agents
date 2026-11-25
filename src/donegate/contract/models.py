"""Pydantic v2 models and structural validation for DoneGate done.yaml contracts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1"


class TaskStatus(str, Enum):
    """Lifecycle status of a task in a DoneGate contract."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    AWAITING_HUMAN = "awaiting_human"


class OnFailStrategy(str, Enum):
    """Action taken when a task fails its checks or scope guard."""

    RETRY = "retry"
    SKIP_AND_FLAG = "skip_and_flag"
    ASK_HUMAN = "ask_human"


class ScopeMode(str, Enum):
    """Enforcement mode for out-of-scope file changes."""

    WARN = "warn"
    BLOCK = "block"
    REVERT_SUGGESTION = "revert-suggestion"


class Criticality(str, Enum):
    """Task importance level."""

    MUST = "must"
    SHOULD = "should"
    NICE = "nice"


def validate_glob_pattern(pattern: str) -> str:
    """Validate that a glob pattern is non-empty and syntactically sound."""
    if not pattern or not pattern.strip():
        raise ValueError("Glob pattern must not be empty or whitespace")
    if "\x00" in pattern:
        raise ValueError("Glob pattern must not contain null bytes")

    # Check balanced character classes [...] outside escaped sequences
    in_class = False
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            i += 2
            continue
        if ch == "[" and not in_class:
            in_class = True
        elif ch == "]" and in_class:
            in_class = False
        i += 1
    if in_class:
        raise ValueError(f"Unclosed character class '[' in glob pattern: {pattern!r}")
    return pattern


class ScopeSpec(BaseModel):
    """Allowed and denied file path globs for a task."""

    model_config = ConfigDict(extra="forbid")

    allow: list[str] = Field(default_factory=lambda: ["**/*"])
    deny: list[str] = Field(default_factory=list)
    ignore_lockfiles: bool = True

    @field_validator("allow", "deny")
    @classmethod
    def _validate_globs(cls, patterns: list[str]) -> list[str]:
        return [validate_glob_pattern(p) for p in patterns]


class BudgetSpec(BaseModel):
    """Resource limits for a single task."""

    model_config = ConfigDict(extra="forbid")

    steps: int | None = Field(default=20, ge=1)
    minutes: float | None = Field(default=30.0, gt=0)
    tokens: int | None = Field(default=None, ge=0)


class UsageCounters(BaseModel):
    """Observed resource usage for a task."""

    model_config = ConfigDict(extra="forbid")

    steps: int = Field(default=0, ge=0)
    minutes: float = Field(default=0.0, ge=0.0)
    tokens: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)


class OnFailSpec(BaseModel):
    """Failure handling policy for a task."""

    model_config = ConfigDict(extra="forbid")

    strategy: OnFailStrategy = OnFailStrategy.RETRY
    max_retries: int = Field(default=3, ge=0, le=20)


class CheckSpec(BaseModel):
    """Configuration for a single check inside a task."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(min_length=1)
    name: str | None = None
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    command: str | None = None
    parser: str | None = None
    path: str | None = None

    def display_name(self) -> str:
        """Return a human-readable identifier for this check."""
        return self.name or self.type


class ProfileBinding(BaseModel):
    """Language profile binding for monorepo / polyglot projects."""

    model_config = ConfigDict(extra="forbid")

    profile: str = Field(min_length=1)
    path: str = "."


class TaskSpec(BaseModel):
    """Executable contract for a single agent task."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    priority: int = Field(default=50, ge=0, le=1000)
    criticality: Criticality = Criticality.MUST
    scope: ScopeSpec = Field(default_factory=ScopeSpec)
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    checks: list[CheckSpec] = Field(min_length=1)
    on_fail: OnFailSpec = Field(default_factory=OnFailSpec)
    status: TaskStatus = TaskStatus.PENDING
    needs_human_approval: bool = False
    usage: UsageCounters = Field(default_factory=UsageCounters)

    @model_validator(mode="after")
    def _validate_objective_checks(self) -> TaskSpec:
        objective = [c for c in self.checks if c.type != "llm_judge"]
        if not objective:
            raise ValueError(
                f"Task {self.id!r} must have at least one objective check "
                "(checks other than 'llm_judge')"
            )
        return self


class Contract(BaseModel):
    """Top-level DoneGate contract (done.yaml)."""

    model_config = ConfigDict(extra="forbid")

    version: str = SCHEMA_VERSION
    goal: str = Field(min_length=1)
    deadline: datetime | str | None = None
    language_profile: str | list[str] | None = None
    profiles: list[ProfileBinding] = Field(default_factory=list)
    scope_mode: ScopeMode = ScopeMode.BLOCK
    tasks: list[TaskSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_task_graph(self) -> Contract:
        seen: set[str] = set()
        duplicates: list[str] = []
        for task in self.tasks:
            if task.id in seen:
                duplicates.append(task.id)
            seen.add(task.id)
        if duplicates:
            raise ValueError(f"Duplicate task IDs found: {', '.join(duplicates)}")

        task_map: dict[str, TaskSpec] = {t.id: t for t in self.tasks}
        for task in self.tasks:
            unknown = [dep for dep in task.depends_on if dep not in task_map]
            if unknown:
                raise ValueError(
                    f"Task {task.id!r} depends on unknown task(s): {', '.join(unknown)}"
                )

        # Detect cycles using 3-color DFS and report the exact cycle path
        state: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=visited
        stack: list[str] = []

        def dfs(node_id: str) -> list[str] | None:
            state[node_id] = 1
            stack.append(node_id)
            for dep in task_map[node_id].depends_on:
                dep_state = state.get(dep, 0)
                if dep_state == 1:
                    cycle_start = stack.index(dep)
                    return stack[cycle_start:] + [dep]
                if dep_state == 0:
                    found = dfs(dep)
                    if found is not None:
                        return found
            stack.pop()
            state[node_id] = 2
            return None

        for task in self.tasks:
            if state.get(task.id, 0) == 0:
                cycle = dfs(task.id)
                if cycle is not None:
                    cycle_str = " -> ".join(cycle)
                    raise ValueError(f"Dependency cycle detected: {cycle_str}")

        return self

    def get_task(self, task_id: str) -> TaskSpec:
        """Return a task by ID or raise KeyError."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise KeyError(f"Unknown task ID: {task_id!r}")

    def to_yaml_dict(self) -> dict[str, Any]:
        """Serialize contract to a clean YAML-compatible dictionary."""
        return self.model_dump(mode="json", exclude_none=True)
