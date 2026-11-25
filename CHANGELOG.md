# Changelog

All notable changes to DoneGate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-25

### Added
- Executable `done.yaml` contract specification with Pydantic v2 validation, cycle detection, and versioned JSON Schema export.
- Language-agnostic check engine (`command`, `test_suite`, `file_exists`, `file_contains`, `json_path`, `http_check`, `lint_clean`, `no_new_lint_errors`, `human_approval`, `llm_judge`) with entry-point plugins and <=15-line failure summaries.
- Pluggable test output parsers for `pytest`, `jest`/`vitest`, `go_test` (`-json`), `cargo_test`, `junit_xml`, `tap`, and `generic`.
- Built-in language profiles and polyglot auto-detection for Python, Node.js, Go, Rust, Java, .NET, Ruby, and PHP.
- Git-based scope guard supporting `warn`, `block`, and `revert-suggestion` modes, renames, deletions, untracked files, and lockfile auto-ignore.
- Supervisor with atomic `.donegate/state.json`, append-only `.donegate/events.log`, budget enforcement, `on_fail` strategies, and deadline warnings.
- Typer + Rich CLI (`init`, `validate`, `next`, `start`, `check`, `status`, `log`, `export`, `integrate`, `doctor`, `report-usage`) with `--json` on every command.
- Agent integrations for `claude_code`, `cursor`, `git`, `generic`, and `mcp` (stdio JSON-RPC 2.0).
- DoneBench 12-task polyglot benchmark harness (`python -m bench.run --agent mock`).
