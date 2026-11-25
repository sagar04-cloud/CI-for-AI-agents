# 20-Second Terminal Demo Script

Record with `asciinema rec demo.cast` or `vhs` to show DoneGate catching a premature "done" and scope violation.

```bash
# 1. Initialize a contract (auto-detects language)
donegate init --goal "Fix discount calculation"

# 2. Start the task (snapshots git baseline + timer)
donegate start python-task

# 3. Agent edits an unrelated file and leaves bug unfixed -> claims done
#    DoneGate blocks completion in <=15 lines:
donegate check python-task
# -> FAILED (2 check(s) failed):
#    - [python-tests] Tests failed (1 failed, 0 passed)
#    - [scope_guard] Scope violation (block): 1 out-of-scope file(s): README.md
#      Next: Revert out-of-scope files or update task scope.

# 4. Agent reverts README.md and fixes the bug -> gate passes!
git restore -- README.md
donegate check python-task
# -> Task python-task passed all checks.
```
