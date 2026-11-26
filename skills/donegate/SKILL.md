---
name: donegate
description: Enforce DoneGate contracts (`done.yaml`), git scope guards, token budgets, and objective checks so AI coding agents use fewer tokens and never claim "done" while checks fail.
---

# DoneGate — CI for AI Agents

Use DoneGate on every coding task in a git repository to **save tokens** and **never claim "done" when work is incomplete**.

## Running DoneGate

1. If `donegate` is on `PATH`, run `donegate ...` directly.
2. Else if `uvx` is available: `uvx --from git+https://github.com/sagar04-cloud/CI-for-AI-agents.git donegate ...`
3. Else install once: `python -m pip install "git+https://github.com/sagar04-cloud/CI-for-AI-agents.git"`

## Token-Saving Rules (Follow Strictly)

- Always pass `--json` (`donegate next --json`, `donegate check <id> --json`) for compact output.
- Do **not** run verbose test suites separately and paste long logs — `donegate check` already returns a `<= 15`-line `summary` with the failing check, key error lines, and one next action.
- Only read and edit files matching the task's `scope.allow` globs; never explore unrelated folders.
- Common `done.yaml` check types (no need to search DoneGate source):
  `test_suite` (`command`, `parser`: `pytest|jest|vitest|go_test|cargo_test|junit_xml|tap|generic`), `lint_clean` (`command`), `command` (`command`), `file_exists` (`path`), `file_contains` (`path`, `pattern`).

## Mandatory Task Loop

1. Initialize contract if `done.yaml` is missing: `donegate init --goal "<goal>"`
2. Pick next task: `donegate next --json`
3. Start task (snapshots git baseline + timer): `donegate start <task-id>`
4. Edit **only** files inside `scope.allow` (avoid `scope.deny`).
5. Verify before finishing: `donegate check <task-id> --json`

## Strict Honesty Rule (Zero False "Done")

- **NEVER** say a task is "done", "fixed", or "working" unless `donegate check <task-id> --json` returned `"passed": true` (exit code `0`) **after your final edit**.
- If `donegate check` fails, hits a budget limit, or requires human approval (`awaiting_human`), or if the same check fails **3 times**:
  **STOP and report the exact blocker** to the user:
  1. Which check failed (name & exit code),
  2. The exact error lines from `summary`, and
  3. Why it is blocked — **never** hide failures or claim success.
