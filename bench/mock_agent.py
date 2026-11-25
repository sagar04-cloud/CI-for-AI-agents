"""Offline mock agent for DoneBench (simulates premature done & scope drift)."""

from __future__ import annotations

from pathlib import Path

from bench.tasks import BenchTask


def run_mock_agent(
    repo: Path,
    task: BenchTask,
    attempt: int,
    with_gate: bool,
    feedback: str = "",
) -> tuple[bool, int]:
    """
    Simulate an AI coding agent attempting `task` in `repo`.

    Returns (claimed_done, tokens_used).
    """
    # Deterministic behavior:
    # - Attempt 1 without gate: simulates an agent that forgets the real fix on half the tasks
    #   and edits an out-of-scope file (README.md) on every 3rd task, yet still claims "done".
    # - Attempt 1 with gate: same initial mistake, which DoneGate catches.
    # - Attempt 2 with gate: reads DoneGate's short feedback, reverts out-of-scope edit, and fixes.
    idx = sum(ord(c) for c in task.id)
    if attempt == 1:
        if idx % 2 == 0:
            # Premature done: doesn't apply the real fix yet
            pass
        else:
            (repo / task.target_file).write_text(task.fixed_content, encoding="utf-8")

        if idx % 3 == 0:
            (repo / task.unrelated_file).write_text(task.unrelated_edit, encoding="utf-8")

        return True, 800

    # Attempt >= 2 (only reached when DoneGate blocks attempt 1)
    if (
        ("Scope violation" in feedback or (repo / task.unrelated_file).exists())
        and task.unrelated_file in task.files
    ):
        # Revert unrelated file back to original
        (repo / task.unrelated_file).write_text(
            task.files[task.unrelated_file], encoding="utf-8"
        )
    (repo / task.target_file).write_text(task.fixed_content, encoding="utf-8")
    return True, 600
