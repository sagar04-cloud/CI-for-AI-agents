# DoneGate

[![CI](https://github.com/sagar04-cloud/CI-for-AI-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/sagar04-cloud/CI-for-AI-agents/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/donegate.svg)](https://pypi.org/project/donegate/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

**CI for AI agents.** *Agents can't say 'done' until the check passes, and can't touch files outside their task.*

---

## Before & After

| Without DoneGate | With DoneGate |
| --- | --- |
| Agent claims "Done!" while tests still fail | `donegate check` blocks completion until every objective check exits 0 |
| Agent edits `README.md` or unrelated modules | Git scope guard detects out-of-scope diffs (`block`, `warn`, `revert-suggestion`) |
| Agent loops infinitely burning tokens | Task budgets (`steps`, `minutes`, `tokens`) halt overruns deterministically |
| Verbose 500-line stack traces flood context | Compact `<=15` line failure summary with failing check, key errors, and next step |

---

## 60-Second Quickstart

```bash
# Install
pip install donegate
# or isolated CLI install:
pipx install donegate
# or run without installing globally:
uvx donegate --help
# or install latest from GitHub:
pip install git+https://github.com/sagar04-cloud/CI-for-AI-agents.git

# In any git repository:
donegate init --goal "Fix discount calculation"
donegate doctor
donegate next
donegate start python-task
donegate check python-task
donegate status
```

All commands support `--json` for machine-readable agent loops.

---

## Contract Reference (`done.yaml`)

```yaml
version: "1"
goal: "Fix authentication bug"
deadline: "2026-12-01T00:00:00Z" # optional
language_profile: python          # optional (auto-detected by donegate init)
scope_mode: block                 # block | warn | revert-suggestion

tasks:
  - id: fix-auth
    title: "Fix token expiry check"
    depends_on: []
    priority: 100
    criticality: must             # must | should | nice
    scope:
      allow: ["src/auth/**/*.py", "tests/test_auth.py"]
      deny: ["src/billing/**"]
      ignore_lockfiles: true
    budget:
      steps: 10
      minutes: 15
      tokens: 20000
    checks:
      - type: test_suite
        command: "pytest"
        parser: pytest
      - type: lint_clean
        command: "ruff check src tests"
    on_fail:
      strategy: retry             # retry | skip_and_flag | ask_human
      max_retries: 3
    needs_human_approval: false
```

Export the versioned JSON Schema anytime with `donegate export --schema`.

---

## Supported Languages (Language-Agnostic Core)

DoneGate is written in Python, but guards repositories in **any** language that has a command returning exit code `0`:

| Language | Profile | Marker Files | Default Parser | Example |
| --- | --- | --- | --- | --- |
| Python | `python` | `pyproject.toml`, `setup.py`, `requirements.txt` | `pytest` | [`examples/python/done.yaml`](examples/python/done.yaml) |
| JavaScript / TypeScript | `node` | `package.json` | `jest` / `vitest` | [`examples/node/done.yaml`](examples/node/done.yaml) |
| Go | `go` | `go.mod` | `go_test` (`-json`) | [`examples/go/done.yaml`](examples/go/done.yaml) |
| Rust | `rust` | `Cargo.toml` | `cargo_test` | [`examples/rust/done.yaml`](examples/rust/done.yaml) |
| Java / Kotlin | `java` | `pom.xml`, `build.gradle*` | `junit_xml` | [`examples/java/done.yaml`](examples/java/done.yaml) |
| C# / .NET | `dotnet` | `*.csproj`, `*.sln` | `junit_xml` | [`examples/dotnet/done.yaml`](examples/dotnet/done.yaml) |
| Ruby | `ruby` | `Gemfile` | `generic` | [`examples/ruby/done.yaml`](examples/ruby/done.yaml) |
| PHP | `php` | `composer.json` | `junit_xml` | [`examples/php/done.yaml`](examples/php/done.yaml) |

Monorepos and polyglot repositories are auto-detected per subdirectory.

---

## Extensibility: Checks, Parsers, Profiles, Integrations

- **Built-in Checks**: `command`, `test_suite`, `file_exists`, `file_contains`, `json_path`, `http_check`, `lint_clean`, `no_new_lint_errors`, `human_approval`, `llm_judge`.
- **Custom Plugins**: Publish third-party checks or test parsers via Python `entry_points` (`donegate.checks` and `donegate.parsers`).
- **Custom Profiles**: Drop `<name>.yaml` into `.donegate/profiles/` in any repo to override or add a language profile.
- **Agent Integrations** (`donegate integrate <name>`):
  - `claude_code`: `CLAUDE.md` snippet + `.claude/settings.json` Stop hook
  - `cursor`: `.cursor/rules/donegate.mdc`
  - `git`: `.git/hooks/pre-commit`
  - `generic`: `DONEGATE_PROMPT.md`
  - `mcp`: `.mcp.json` + zero-dependency stdio MCP server (`donegate_next`, `donegate_start`, `donegate_check`, `donegate_status`)

---

## DoneBench Results

Run offline with `python -m bench.run --agent mock` across 12 tasks in 4 languages (Python, TypeScript, Go, Rust):

| Mode | Tasks | Truly Passed | False-Done Rate | Total Tokens | Total Time (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `baseline` (no gate) | 12 | 6/12 | 50.0% (6) | 9600 | 3.97 |
| `donegate` | 12 | 12/12 | 0.0% (0) | 13200 | 4.78 |

**Honest Limitations**:
- The `mock` agent deterministically simulates premature "done" claims and out-of-scope edits to verify the harness offline; live LLM results depend on the model and prompt.
- DoneGate's scope guard relies on `git` working-tree diffs; repositories without `git` cannot enforce scope diffs.
- `done.yaml` executes shell commands (`command`, `test_suite`, `lint_clean`) — only run contracts from trusted repositories.

See [`docs/demo.md`](docs/demo.md) for a 20-second terminal demo script.
