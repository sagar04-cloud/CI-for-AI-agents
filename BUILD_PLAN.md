# DoneGate Build Plan (Dogfood Contract)

```yaml
version: "1"
goal: "Build DoneGate: an open-source language-agnostic CI gate for AI agents."
language_profile: python

tasks:
  - id: phase-0-setup
    title: "Phase 0: Project scaffold, pyproject, lint/type/test config"
    depends_on: []
    priority: 100
    status: done
    scope:
      allow:
        - "BUILD_PLAN.md"
        - "ASSUMPTIONS.md"
        - "FUTURE_IDEAS.md"
        - "pyproject.toml"
        - ".gitignore"
        - "src/donegate/__init__.py"
        - "tests/test_smoke.py"
      deny: []
    budget:
      steps: 15
      minutes: 20
      tokens: 0
    checks:
      - type: command
        command: "pytest"
      - type: command
        command: "ruff check src tests"
      - type: command
        command: "mypy src"

  - id: phase-1-contract
    title: "Phase 1: Contract spec (done.yaml) and JSON Schema"
    depends_on: [phase-0-setup]
    priority: 95
    status: done
    scope:
      allow:
        - "src/donegate/contract/**"
        - "tests/test_contract.py"
        - "BUILD_PLAN.md"
      deny: []
    budget:
      steps: 20
      minutes: 30
      tokens: 0
    checks:
      - type: command
        command: "pytest tests/test_contract.py"
      - type: command
        command: "ruff check src tests"
      - type: command
        command: "mypy src"

  - id: phase-2-checks
    title: "Phase 2: Language-agnostic check engine and test parsers"
    depends_on: [phase-1-contract]
    priority: 90
    status: done
    scope:
      allow:
        - "src/donegate/checks/**"
        - "src/donegate/parsers/**"
        - "tests/test_checks.py"
        - "tests/test_parsers.py"
        - "tests/fixtures/**"
        - "BUILD_PLAN.md"
      deny: []
    budget:
      steps: 30
      minutes: 45
      tokens: 0
    checks:
      - type: command
        command: "pytest tests/test_checks.py tests/test_parsers.py"
      - type: command
        command: "ruff check src tests"
      - type: command
        command: "mypy src"

  - id: phase-3-profiles
    title: "Phase 3: Language profiles and auto-detection"
    depends_on: [phase-2-checks]
    priority: 85
    status: done
    scope:
      allow:
        - "profiles/**"
        - "src/donegate/profiles/**"
        - "tests/test_profiles.py"
        - "tests/fixtures/projects/**"
        - "BUILD_PLAN.md"
      deny: []
    budget:
      steps: 25
      minutes: 35
      tokens: 0
    checks:
      - type: command
        command: "pytest tests/test_profiles.py"
      - type: command
        command: "ruff check src tests"
      - type: command
        command: "mypy src"

  - id: phase-4-scope
    title: "Phase 4: Git-based scope guard"
    depends_on: [phase-3-profiles]
    priority: 80
    status: done
    scope:
      allow:
        - "src/donegate/scope/**"
        - "tests/test_scope.py"
        - "BUILD_PLAN.md"
      deny: []
    budget:
      steps: 20
      minutes: 30
      tokens: 0
    checks:
      - type: command
        command: "pytest tests/test_scope.py"
      - type: command
        command: "ruff check src tests"
      - type: command
        command: "mypy src"

  - id: phase-5-supervisor
    title: "Phase 5: Supervisor, atomic state.json, events.log"
    depends_on: [phase-4-scope]
    priority: 75
    status: done
    scope:
      allow:
        - "src/donegate/supervisor/**"
        - "tests/test_supervisor.py"
        - "BUILD_PLAN.md"
      deny: []
    budget:
      steps: 25
      minutes: 35
      tokens: 0
    checks:
      - type: command
        command: "pytest tests/test_supervisor.py"
      - type: command
        command: "ruff check src tests"
      - type: command
        command: "mypy src"

  - id: phase-6-cli-integrations
    title: "Phase 6: CLI (Typer/Rich) and agent integrations"
    depends_on: [phase-5-supervisor]
    priority: 70
    status: done
    scope:
      allow:
        - "src/donegate/cli.py"
        - "src/donegate/integrations/**"
        - "src/donegate/templates/**"
        - "tests/test_cli.py"
        - "tests/test_integrations.py"
        - "BUILD_PLAN.md"
      deny: []
    budget:
      steps: 30
      minutes: 45
      tokens: 0
    checks:
      - type: command
        command: "pytest tests/test_cli.py tests/test_integrations.py"
      - type: command
        command: "ruff check src tests"
      - type: command
        command: "mypy src"

  - id: phase-7-bench
    title: "Phase 7: DoneBench benchmark suite"
    depends_on: [phase-6-cli-integrations]
    priority: 65
    status: done
    scope:
      allow:
        - "bench/**"
        - "tests/test_bench.py"
        - "BUILD_PLAN.md"
      deny: []
    budget:
      steps: 30
      minutes: 45
      tokens: 0
    checks:
      - type: command
        command: "python -m bench.run --agent mock"
      - type: command
        command: "pytest tests/test_bench.py"
      - type: command
        command: "ruff check src tests bench"
      - type: command
        command: "mypy src bench"

  - id: phase-8-docs
    title: "Phase 8: Documentation, examples, and launch kit"
    depends_on: [phase-7-bench]
    priority: 60
    status: done
    scope:
      allow:
        - "README.md"
        - "CONTRIBUTING.md"
        - "CHANGELOG.md"
        - "LICENSE"
        - "SECURITY.md"
        - "CODE_OF_CONDUCT.md"
        - "FUTURE_IDEAS.md"
        - "docs/**"
        - "examples/**"
        - "tests/test_examples.py"
        - "BUILD_PLAN.md"
      deny: []
    budget:
      steps: 25
      minutes: 35
      tokens: 0
    checks:
      - type: command
        command: "pytest tests/test_examples.py"
      - type: command
        command: "ruff check src tests bench"

  - id: phase-9-packaging
    title: "Phase 9: Packaging, GitHub Actions, Dockerfile, Release Checklist"
    depends_on: [phase-8-docs]
    priority: 55
    status: done
    scope:
      allow:
        - "pyproject.toml"
        - ".github/**"
        - "Dockerfile"
        - "docs/RELEASE_CHECKLIST.md"
        - "README.md"
        - "BUILD_PLAN.md"
      deny: []
    budget:
      steps: 20
      minutes: 30
      tokens: 0
    checks:
      - type: command
        command: "python -m build"
      - type: command
        command: "pytest --cov=donegate"
      - type: command
        command: "ruff check src tests bench"
      - type: command
        command: "mypy src"
```

---

## Release History
- **v0.1.0** (`2026-11-25`): Phases 0–9 completed.
- **v1.1.0** (`2026-11-26`): Added `check --all`, `reset`, `report`, `plan`, `ui`, OTLP export, 13 language profiles/examples, 10 agent integrations, `SKILL.md` / `.claude-plugin`, and live polyglot E2E CI.
