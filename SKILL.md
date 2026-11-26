---
name: donegate
description: Enforce DoneGate contracts (`done.yaml`), git scope guards, budgets, and objective checks before any AI coding agent claims a task is done.
---

# DoneGate — CI for AI Agents

Use DoneGate on every coding task in a git repository so you never claim "done" with failing tests or out-of-scope edits.

## Running DoneGate (Zero Pre-Install Needed)

If `donegate` is already installed on `PATH`, run `donegate ...` directly.
Otherwise, run it directly from this repository using `uvx` or `pipx`:

```bash
uvx --from git+https://github.com/sagar04-cloud/CI-for-AI-agents.git donegate --help
```

## Mandatory Task Loop

1. **Initialize or inspect contract** (if `done.yaml` does not exist yet):
   ```bash
   donegate init --goal "<user goal>"
   ```
2. **Pick the next runnable task**:
   ```bash
   donegate next --json
   ```
3. **Start the task** (snapshots git baseline and starts budget timer):
   ```bash
   donegate start <task-id>
   ```
4. **Edit ONLY files allowed by the task's `scope.allow` globs** (avoid `scope.deny`).
5. **Run the gate before claiming completion**:
   ```bash
   donegate check <task-id> --json
   ```
   - If `passed` is `false`, read the compact `<= 15`-line `summary`, fix the failing check or revert out-of-scope edits, and re-run `donegate check <task-id>`.
   - **Never say "done" until `donegate check <task-id>` exits with code `0`.**
6. **Check overall status or cost report**:
   ```bash
   donegate status
   donegate report
   ```
