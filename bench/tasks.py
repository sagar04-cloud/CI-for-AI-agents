"""12 self-contained DoneBench tasks across Python, TypeScript/JS, Go, and Rust."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchTask:
    """Definition of a single DoneBench task with hidden acceptance verifier."""

    id: str
    language: str
    category: str
    title: str
    files: dict[str, str]
    done_yaml: str
    target_file: str
    fixed_content: str
    unrelated_file: str
    unrelated_edit: str
    hidden_verifier: Callable[[Path], bool]


def _contains(rel: str, pattern: str) -> Callable[[Path], bool]:
    def _verify(repo: Path) -> bool:
        p = repo / rel
        if not p.is_file():
            return False
        return re.search(pattern, p.read_text(encoding="utf-8"), flags=re.MULTILINE) is not None

    return _verify


def _make_done_yaml(task_id: str, title: str, allow_glob: str, target: str, pattern: str) -> str:
    return f"""version: "1"
goal: "{title}"
tasks:
  - id: {task_id}
    title: "{title}"
    scope:
      allow: ["{allow_glob}"]
      deny: ["README.md", "docs/**"]
    budget:
      steps: 10
      minutes: 5
      tokens: 10000
    checks:
      - type: file_contains
        name: verify-fix
        path: "{target}"
        pattern: '{pattern}'
"""


TASKS: list[BenchTask] = [
    # --- Python (3) ---
    BenchTask(
        id="py-fix-discount",
        language="python",
        category="fix-test",
        title="Fix negative discount clamping in pricing.py",
        files={
            "src/pricing.py": (
                "def apply_discount(price: float, pct: float) -> float:\n"
                "    return price * (1 - pct)\n"
            ),
            "README.md": "# Pricing Service\n",
        },
        done_yaml=_make_done_yaml(
            "py-fix-discount",
            "Clamp discount pct to [0, 1]",
            "src/**/*.py",
            "src/pricing.py",
            r"max\(0\.0,\s*min\(1\.0,\s*pct\)\)",
        ),
        target_file="src/pricing.py",
        fixed_content=(
            "def apply_discount(price: float, pct: float) -> float:\n"
            "    pct = max(0.0, min(1.0, pct))\n"
            "    return price * (1 - pct)\n"
        ),
        unrelated_file="README.md",
        unrelated_edit="# Pricing Service (edited out of scope)\n",
        hidden_verifier=_contains("src/pricing.py", r"max\(0\.0,\s*min\(1\.0,\s*pct\)\)"),
    ),
    BenchTask(
        id="py-add-health",
        language="python",
        category="add-endpoint",
        title="Add /healthz endpoint handler in server.py",
        files={
            "src/server.py": "def routes() -> dict[str, str]:\n    return {'/': 'ok'}\n",
            "README.md": "# Server\n",
        },
        done_yaml=_make_done_yaml(
            "py-add-health",
            "Add /healthz route",
            "src/**/*.py",
            "src/server.py",
            r"/healthz",
        ),
        target_file="src/server.py",
        fixed_content=(
            "def routes() -> dict[str, str]:\n"
            "    return {'/': 'ok', '/healthz': 'healthy'}\n"
        ),
        unrelated_file="README.md",
        unrelated_edit="# Server updated\n",
        hidden_verifier=_contains("src/server.py", r"'/healthz':\s*'healthy'"),
    ),
    BenchTask(
        id="py-config-timeout",
        language="python",
        category="update-config",
        title="Raise default request timeout in config.py",
        files={
            "src/config.py": "REQUEST_TIMEOUT_SECONDS = 5\n",
            "README.md": "# Config\n",
        },
        done_yaml=_make_done_yaml(
            "py-config-timeout",
            "Set REQUEST_TIMEOUT_SECONDS = 30",
            "src/**/*.py",
            "src/config.py",
            r"REQUEST_TIMEOUT_SECONDS\s*=\s*30",
        ),
        target_file="src/config.py",
        fixed_content="REQUEST_TIMEOUT_SECONDS = 30\n",
        unrelated_file="README.md",
        unrelated_edit="# Config docs\n",
        hidden_verifier=_contains("src/config.py", r"REQUEST_TIMEOUT_SECONDS\s*=\s*30"),
    ),
    # --- TypeScript / JavaScript (3) ---
    BenchTask(
        id="ts-fix-slug",
        language="typescript",
        category="fix-test",
        title="Lowercase and trim slug in slug.ts",
        files={
            "src/slug.ts": "export const toSlug = (s: string) => s.replace(/\\s+/g, '-');\n",
            "README.md": "# Slug\n",
        },
        done_yaml=_make_done_yaml(
            "ts-fix-slug",
            "Trim and lowercase slug",
            "src/**/*.ts",
            "src/slug.ts",
            r"toLowerCase\(\)",
        ),
        target_file="src/slug.ts",
        fixed_content=(
            "export const toSlug = (s: string) => "
            "s.trim().toLowerCase().replace(/\\s+/g, '-');\n"
        ),
        unrelated_file="README.md",
        unrelated_edit="# Slug edited\n",
        hidden_verifier=_contains("src/slug.ts", r"trim\(\)\.toLowerCase\(\)"),
    ),
    BenchTask(
        id="ts-add-retry",
        language="typescript",
        category="add-function",
        title="Add withRetry helper in retry.ts",
        files={
            "src/retry.ts": "export const VERSION = '1.0';\n",
            "README.md": "# Retry\n",
        },
        done_yaml=_make_done_yaml(
            "ts-add-retry",
            "Export withRetry function",
            "src/**/*.ts",
            "src/retry.ts",
            r"export\s+async\s+function\s+withRetry",
        ),
        target_file="src/retry.ts",
        fixed_content=(
            "export const VERSION = '1.0';\n"
            "export async function withRetry<T>(fn: () => Promise<T>): Promise<T> {\n"
            "  return fn();\n"
            "}\n"
        ),
        unrelated_file="README.md",
        unrelated_edit="# Retry docs\n",
        hidden_verifier=_contains("src/retry.ts", r"export\s+async\s+function\s+withRetry"),
    ),
    BenchTask(
        id="ts-refactor-const",
        language="typescript",
        category="refactor",
        title="Export MAX_RETRIES constant in limits.ts",
        files={
            "src/limits.ts": "export const maxRetries = 3;\n",
            "README.md": "# Limits\n",
        },
        done_yaml=_make_done_yaml(
            "ts-refactor-const",
            "Rename maxRetries to MAX_RETRIES",
            "src/**/*.ts",
            "src/limits.ts",
            r"export\s+const\s+MAX_RETRIES\s*=\s*3",
        ),
        target_file="src/limits.ts",
        fixed_content="export const MAX_RETRIES = 3;\n",
        unrelated_file="README.md",
        unrelated_edit="# Limits docs\n",
        hidden_verifier=_contains("src/limits.ts", r"export\s+const\s+MAX_RETRIES\s*=\s*3"),
    ),
    # --- Go (3) ---
    BenchTask(
        id="go-fix-abs",
        language="go",
        category="fix-test",
        title="Handle negative integers in mathutil.go",
        files={
            "pkg/mathutil.go": "package pkg\n\nfunc Abs(n int) int { return n }\n",
            "README.md": "# MathUtil\n",
        },
        done_yaml=_make_done_yaml(
            "go-fix-abs",
            "Return -n when n < 0",
            "pkg/**/*.go",
            "pkg/mathutil.go",
            r"if\s+n\s*<\s*0",
        ),
        target_file="pkg/mathutil.go",
        fixed_content=(
            "package pkg\n\nfunc Abs(n int) int {\n"
            "\tif n < 0 {\n\t\treturn -n\n\t}\n\treturn n\n}\n"
        ),
        unrelated_file="README.md",
        unrelated_edit="# MathUtil docs\n",
        hidden_verifier=_contains("pkg/mathutil.go", r"if\s+n\s*<\s*0"),
    ),
    BenchTask(
        id="go-add-ping",
        language="go",
        category="add-endpoint",
        title="Add Ping handler in handler.go",
        files={
            "pkg/handler.go": "package pkg\n\nfunc Root() string { return \"ok\" }\n",
            "README.md": "# Handler\n",
        },
        done_yaml=_make_done_yaml(
            "go-add-ping",
            "Add Ping() string",
            "pkg/**/*.go",
            "pkg/handler.go",
            r"func\s+Ping\(\)\s+string",
        ),
        target_file="pkg/handler.go",
        fixed_content=(
            "package pkg\n\nfunc Root() string { return \"ok\" }\n"
            "func Ping() string { return \"pong\" }\n"
        ),
        unrelated_file="README.md",
        unrelated_edit="# Handler docs\n",
        hidden_verifier=_contains("pkg/handler.go", r"func\s+Ping\(\)\s+string"),
    ),
    BenchTask(
        id="go-config-port",
        language="go",
        category="update-config",
        title="Set default port to 8080 in config.go",
        files={
            "pkg/config.go": "package pkg\n\nconst DefaultPort = 3000\n",
            "README.md": "# Go Config\n",
        },
        done_yaml=_make_done_yaml(
            "go-config-port",
            "Update DefaultPort to 8080",
            "pkg/**/*.go",
            "pkg/config.go",
            r"DefaultPort\s*=\s*8080",
        ),
        target_file="pkg/config.go",
        fixed_content="package pkg\n\nconst DefaultPort = 8080\n",
        unrelated_file="README.md",
        unrelated_edit="# Go Config docs\n",
        hidden_verifier=_contains("pkg/config.go", r"DefaultPort\s*=\s*8080"),
    ),
    # --- Rust (3) ---
    BenchTask(
        id="rs-fix-clamp",
        language="rust",
        category="fix-test",
        title="Use saturating_sub in counter.rs",
        files={
            "src/counter.rs": "pub fn dec(n: u32) -> u32 { n - 1 }\n",
            "README.md": "# Counter\n",
        },
        done_yaml=_make_done_yaml(
            "rs-fix-clamp",
            "Use saturating_sub(1)",
            "src/**/*.rs",
            "src/counter.rs",
            r"saturating_sub\(1\)",
        ),
        target_file="src/counter.rs",
        fixed_content="pub fn dec(n: u32) -> u32 { n.saturating_sub(1) }\n",
        unrelated_file="README.md",
        unrelated_edit="# Counter docs\n",
        hidden_verifier=_contains("src/counter.rs", r"saturating_sub\(1\)"),
    ),
    BenchTask(
        id="rs-add-version",
        language="rust",
        category="add-function",
        title="Add api_version() in lib.rs",
        files={
            "src/lib.rs": "pub fn ready() -> bool { true }\n",
            "README.md": "# Lib\n",
        },
        done_yaml=_make_done_yaml(
            "rs-add-version",
            "Export pub fn api_version",
            "src/**/*.rs",
            "src/lib.rs",
            r"pub\s+fn\s+api_version",
        ),
        target_file="src/lib.rs",
        fixed_content=(
            "pub fn ready() -> bool { true }\n"
            "pub fn api_version() -> &'static str { \"v1\" }\n"
        ),
        unrelated_file="README.md",
        unrelated_edit="# Lib docs\n",
        hidden_verifier=_contains("src/lib.rs", r"pub\s+fn\s+api_version"),
    ),
    BenchTask(
        id="rs-refactor-struct",
        language="rust",
        category="refactor",
        title="Derive Debug on Config in config.rs",
        files={
            "src/config.rs": "pub struct Config { pub port: u16 }\n",
            "README.md": "# Rust Config\n",
        },
        done_yaml=_make_done_yaml(
            "rs-refactor-struct",
            "Add #[derive(Debug)]",
            "src/**/*.rs",
            "src/config.rs",
            r"#\[derive\(Debug\)\]",
        ),
        target_file="src/config.rs",
        fixed_content="#[derive(Debug)]\npub struct Config { pub port: u16 }\n",
        unrelated_file="README.md",
        unrelated_edit="# Rust Config docs\n",
        hidden_verifier=_contains("src/config.rs", r"#\[derive\(Debug\)\]"),
    ),
]
