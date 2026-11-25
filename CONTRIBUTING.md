# Contributing to DoneGate

Thank you for your interest in contributing to DoneGate!

## Development Setup

```bash
git clone https://github.com/sagar04-cloud/CI-for-AI-agents.git
cd CI-for-AI-agents
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running Checks

```bash
pytest --cov=donegate
ruff check src tests bench
mypy src bench
```

## Adding a Language Profile

1. Add `<lang>.yaml` under `profiles/`.
2. Include `name`, `detection_files`, `default_test_command`, `test_parser`, `lint_command`, and `default_scope`.
3. Add a detection test in `tests/test_profiles.py` and an example in `examples/<lang>/done.yaml`.

## Adding a Check or Test Parser

Implement `CheckHandler` (`src/donegate/checks/base.py`) or `TestParser` (`src/donegate/parsers/base.py`), or publish an external package using Python `entry_points` (`donegate.checks` / `donegate.parsers`).
