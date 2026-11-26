---
name: donegate
description: Pro-engineer workflow + DoneGate contract enforcement (`done.yaml`), git scope guards, and 1-command verification so AI agents use fewer tokens, design better software/UI, and never claim "done" while checks fail.
---

# DoneGate — Pro-Engineer & Low-Token CI for AI Agents

Follow this protocol on every coding task so you act like a **principal engineer**, spend **minimal tokens**, and **never say "done" when work is incomplete**.

## 1. Pro-Engineer Design & Quality Standard

- **Plan cleanly before editing**: Pick the right modular structure first; never dump everything into one giant file.
- **No placeholders or half-done work**: Never leave `TODO`, dummy data, broken links, or unimplemented handlers.
- **Web / JS / React / UI tasks**:
  - Build semantic HTML, clean modular components, responsive mobile+desktop layouts (CSS Grid/Flexbox), accessible contrast/labels, and cohesive typography/spacing.
  - Keep components small and reusable; verify builds (`npm run build` / `tsc --noEmit`) and unit tests pass.

## 2. Token-Saving Execution Rules

- **Use 1 command (`donegate verify --json`)** instead of running separate `init` + `next` + `start` + `check` calls unless managing multi-task dependencies.
- **Always pass `--json`** for compact structured output.
- **Never paste or re-run huge test logs** — `donegate verify --json` returns a `<= 15`-line `summary` with the failing check, key error lines, and one next action.
- **Batch reads & edits** in parallel; only touch files inside `scope.allow`.
- **Running DoneGate**:
  1. `donegate ...` (if on `PATH`)
  2. Else `uvx --from git+https://github.com/sagar04-cloud/CI-for-AI-agents.git donegate ...`
  3. Else `python -m pip install "git+https://github.com/sagar04-cloud/CI-for-AI-agents.git"`

## 3. Fast Workflow (`donegate verify`)

1. Do your design & implementation cleanly inside the project.
2. Run **one** command to auto-init (if needed), start, and verify scope + checks:
   ```bash
   donegate verify --goal "<goal>" --json
   ```
   *(For multi-task contracts, use `donegate next --json`, `donegate start <id>`, `donegate check <id> --json`.)*
   Common `done.yaml` check types: `test_suite`, `lint_clean`, `command`, `file_exists`, `file_contains`, `json_path`.

## 4. Strict Honesty Rule (Zero False "Done")

- **NEVER** say a task is "done", "working", or "accurate" unless `donegate verify --json` (or `donegate check <id> --json`) returned `"passed": true` (exit code `0`) **after your final edit**.
- If a check fails, hits a budget limit, or fails 3 times: **STOP and report briefly**:
  1. Which check failed,
  2. The exact error lines from `summary`, and
  3. What is blocking completion — never hide errors or claim success.
