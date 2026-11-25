"""Built-in language-agnostic checks for DoneGate."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from donegate.checks.base import CheckContext, CheckRegistry, CheckResult
from donegate.contract.models import CheckSpec
from donegate.parsers import get_parser_registry


def _run_shell(command: str, cwd: Path, timeout: int) -> tuple[int, str, str, bool]:
    """Execute a shell command cross-platform and return (exit_code, stdout, stderr, timed_out)."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as exc:
        out = (
            exc.stdout.decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        err = (
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        return 124, out, err, True


def _tail(text: str, n: int = 6) -> list[str]:
    return [ln.rstrip() for ln in text.splitlines() if ln.strip()][-n:]


class CommandCheck:
    """Run an arbitrary shell command and require exit code 0."""

    check_type = "command"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        cmd = getattr(spec, "command", None)
        if not isinstance(cmd, str) or not cmd.strip():
            return CheckResult(
                passed=False,
                message="command check requires a non-empty 'command' field",
                suggested_action="Set 'command' in the check configuration.",
            )
        code, stdout, stderr, timed_out = _run_shell(cmd, context.repo_root, spec.timeout_seconds)
        if timed_out:
            return CheckResult(
                passed=False,
                message=f"Command timed out after {spec.timeout_seconds}s: {cmd}",
                evidence={"exit_code": code, "stderr_tail": _tail(stderr or stdout)},
                suggested_action=f"Optimize or increase timeout_seconds for '{cmd}'.",
            )
        passed = code == 0
        return CheckResult(
            passed=passed,
            message=f"Command exited with {code}" if not passed else "Command passed",
            evidence={
                "command": cmd,
                "exit_code": code,
                "stdout_tail": _tail(stdout),
                "stderr_tail": _tail(stderr),
            },
            suggested_action="" if passed else f"Fix the error reported by `{cmd}` and re-run.",
        )


class TestSuiteCheck:
    """Run a test command and parse its output with a pluggable parser."""

    check_type = "test_suite"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        cmd = getattr(spec, "command", None)
        if not isinstance(cmd, str) or not cmd.strip():
            return CheckResult(
                passed=False,
                message="test_suite check requires a 'command' field",
                suggested_action="Provide the test runner command.",
            )
        parser_name = str(getattr(spec, "parser", "generic"))
        code, stdout, stderr, timed_out = _run_shell(cmd, context.repo_root, spec.timeout_seconds)
        if timed_out:
            return CheckResult(
                passed=False,
                message=f"Test suite timed out after {spec.timeout_seconds}s",
                evidence={"exit_code": code},
                suggested_action="Fix hanging tests or raise timeout_seconds.",
            )

        # If junit_xml specifies a report_file, read XML from that file
        report_file = getattr(spec, "report_file", None)
        parser_stdout = stdout
        if isinstance(report_file, str) and report_file:
            xml_path = context.repo_root / report_file
            if xml_path.exists():
                parser_stdout = xml_path.read_text(encoding="utf-8", errors="replace")

        parser = get_parser_registry().get(parser_name)
        parsed = parser.parse(parser_stdout, stderr, code)
        passed = code == 0 and parsed.failed == 0
        msg = (
            f"Tests passed ({parsed.passed} passed, {parsed.skipped} skipped)"
            if passed
            else f"Tests failed ({parsed.failed} failed, {parsed.passed} passed)"
        )
        failing_preview = ", ".join(parsed.failing_test_names[:3]) or "see output"
        return CheckResult(
            passed=passed,
            message=msg,
            evidence={
                "parser": parser_name,
                "exit_code": code,
                **parsed.model_dump(),
            },
            suggested_action="" if passed else f"Fix failing test(s): {failing_preview}.",
        )


class FileExistsCheck:
    """Verify one or more files exist relative to repo_root."""

    check_type = "file_exists"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        raw_paths = getattr(spec, "paths", None) or getattr(spec, "path", None)
        if isinstance(raw_paths, str):
            paths = [raw_paths]
        elif isinstance(raw_paths, list):
            paths = [str(p) for p in raw_paths]
        else:
            return CheckResult(
                passed=False,
                message="file_exists requires 'path' or 'paths'",
                suggested_action="Add 'path: ...' to file_exists check.",
            )

        missing = [p for p in paths if not (context.repo_root / p).exists()]
        passed = len(missing) == 0
        msg = "All required files exist" if passed else f"Missing file(s): {', '.join(missing)}"
        return CheckResult(
            passed=passed,
            message=msg,
            evidence={"checked": paths, "missing": missing},
            suggested_action="" if passed else f"Create missing file(s): {', '.join(missing[:3])}.",
        )


class FileContainsCheck:
    """Verify a file matches (or does not match) a regular expression."""

    check_type = "file_contains"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        rel_path = getattr(spec, "path", None)
        pattern = getattr(spec, "pattern", None)
        negate = bool(getattr(spec, "negate", False))
        if not isinstance(rel_path, str) or not isinstance(pattern, str):
            return CheckResult(
                passed=False,
                message="file_contains requires 'path' and 'pattern'",
                suggested_action="Specify both 'path' and 'pattern'.",
            )
        target = context.repo_root / rel_path
        if not target.is_file():
            return CheckResult(
                passed=False,
                message=f"File not found: {rel_path}",
                suggested_action=f"Create {rel_path} first.",
            )
        content = target.read_text(encoding="utf-8", errors="replace")
        matched = re.search(pattern, content, flags=re.MULTILINE) is not None
        passed = (not matched) if negate else matched
        status_word = "unexpectedly found" if negate else "not found"
        return CheckResult(
            passed=passed,
            message=(
                f"Pattern {pattern!r} check passed on {rel_path}"
                if passed
                else f"Pattern {pattern!r} {status_word} in {rel_path}"
            ),
            evidence={"path": rel_path, "pattern": pattern, "negate": negate},
            suggested_action="" if passed else f"Update {rel_path} to satisfy pattern {pattern!r}.",
        )


def _resolve_json_path(data: Any, expr: str) -> tuple[bool, Any]:
    """Resolve simple dot/bracket JSON path like `$.a.b[0].c` or `scripts.test`."""
    cleaned = expr.strip()
    if cleaned.startswith("$."):
        cleaned = cleaned[2:]
    elif cleaned == "$":
        return True, data

    cur = data
    tokens = re.findall(r"[^.\[\]]+|\[\d+\]", cleaned)
    for tok in tokens:
        if tok.startswith("[") and tok.endswith("]"):
            idx = int(tok[1:-1])
            if not isinstance(cur, list) or idx >= len(cur):
                return False, None
            cur = cur[idx]
        else:
            if not isinstance(cur, dict) or tok not in cur:
                return False, None
            cur = cur[tok]
    return True, cur


class JsonPathCheck:
    """Assert existence or equality of a value at a JSON path inside a file."""

    check_type = "json_path"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        rel_path = getattr(spec, "path", None)
        expr = getattr(spec, "json_path", None) or getattr(spec, "query", None)
        if not isinstance(rel_path, str) or not isinstance(expr, str):
            return CheckResult(
                passed=False,
                message="json_path requires 'path' and 'json_path'",
                suggested_action="Specify 'path' and 'json_path'.",
            )
        target = context.repo_root / rel_path
        if not target.is_file():
            return CheckResult(
                passed=False,
                message=f"JSON file not found: {rel_path}",
                suggested_action=f"Create {rel_path}.",
            )
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return CheckResult(
                passed=False,
                message=f"Invalid JSON in {rel_path}: {exc}",
                suggested_action=f"Fix JSON syntax in {rel_path}.",
            )

        found, value = _resolve_json_path(data, expr)
        if not found:
            return CheckResult(
                passed=False,
                message=f"JSON path {expr!r} not found in {rel_path}",
                suggested_action=f"Add {expr!r} to {rel_path}.",
            )

        if hasattr(spec, "equals"):
            expected = spec.equals
            passed = value == expected
            return CheckResult(
                passed=passed,
                message=(
                    f"JSON path {expr!r} == {expected!r}"
                    if passed
                    else f"JSON path {expr!r} is {value!r}, expected {expected!r}"
                ),
                evidence={
                    "path": rel_path,
                    "json_path": expr,
                    "actual": value,
                    "expected": expected,
                },
                suggested_action="" if passed else f"Set {expr!r} to {expected!r} in {rel_path}.",
            )

        return CheckResult(
            passed=True,
            message=f"JSON path {expr!r} exists in {rel_path}",
            evidence={"path": rel_path, "json_path": expr, "actual": value},
        )


class HttpCheck:
    """Perform an HTTP request and verify status code and optional body substring."""

    check_type = "http_check"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        url = getattr(spec, "url", None)
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return CheckResult(
                passed=False,
                message="http_check requires a valid http(s) 'url'",
                suggested_action="Provide an http:// or https:// URL.",
            )
        method = str(getattr(spec, "method", "GET")).upper()
        expected_status = int(getattr(spec, "expected_status", 200))
        body_contains = getattr(spec, "body_contains", None)

        req = urllib.request.Request(url=url, method=method)
        try:
            with urllib.request.urlopen(req, timeout=spec.timeout_seconds) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read().decode("utf-8", errors="replace")
        except Exception as exc:
            return CheckResult(
                passed=False,
                message=f"HTTP request failed: {exc}",
                evidence={"url": url, "method": method},
                suggested_action=f"Ensure {url} is reachable and retry.",
            )

        status_ok = status == expected_status
        body_ok = True
        if isinstance(body_contains, str) and body_contains:
            body_ok = body_contains in body

        passed = status_ok and body_ok
        msg = (
            f"HTTP {method} {url} returned {status}"
            if passed
            else f"HTTP {method} {url} failed (status={status}, expected={expected_status})"
        )
        return CheckResult(
            passed=passed,
            message=msg,
            evidence={"url": url, "status": status, "expected_status": expected_status},
            suggested_action=(
                "" if passed else f"Fix endpoint {url} to return HTTP {expected_status}."
            ),
        )


class LintCleanCheck:
    """Run a linter command and require zero errors (exit code 0)."""

    check_type = "lint_clean"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        cmd = getattr(spec, "command", None)
        if not isinstance(cmd, str) or not cmd.strip():
            return CheckResult(
                passed=False,
                message="lint_clean requires a 'command' field",
                suggested_action="Provide the linter command.",
            )
        code, stdout, stderr, timed_out = _run_shell(cmd, context.repo_root, spec.timeout_seconds)
        if timed_out:
            return CheckResult(
                passed=False,
                message=f"Linter timed out after {spec.timeout_seconds}s",
                suggested_action="Increase timeout_seconds or scope the lint command.",
            )
        passed = code == 0
        combined = f"{stdout}\n{stderr}"
        return CheckResult(
            passed=passed,
            message="Lint clean" if passed else f"Linter failed with exit code {code}",
            evidence={"command": cmd, "exit_code": code, "key_error_lines": _tail(combined, 6)},
            suggested_action="" if passed else f"Fix lint issues reported by `{cmd}`.",
        )


class NoNewLintErrorsCheck:
    """Allow existing lint baseline errors but fail if error count increases."""

    check_type = "no_new_lint_errors"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        cmd = getattr(spec, "command", None)
        if not isinstance(cmd, str) or not cmd.strip():
            return CheckResult(
                passed=False,
                message="no_new_lint_errors requires a 'command' field",
                suggested_action="Provide the linter command.",
            )
        baseline = int(
            getattr(
                spec,
                "baseline_errors",
                context.lint_baselines.get(spec.display_name(), 0),
            )
        )
        code, stdout, stderr, timed_out = _run_shell(cmd, context.repo_root, spec.timeout_seconds)
        if timed_out:
            return CheckResult(
                passed=False,
                message=f"Linter timed out after {spec.timeout_seconds}s",
                suggested_action="Increase timeout_seconds.",
            )
        if code == 0:
            return CheckResult(
                passed=True,
                message="Zero lint errors",
                evidence={"errors": 0, "baseline": baseline},
            )
        output_lines = [ln for ln in f"{stdout}\n{stderr}".splitlines() if ln.strip()]
        error_count = len(output_lines)
        passed = error_count <= baseline
        return CheckResult(
            passed=passed,
            message=(
                f"Lint errors ({error_count}) within baseline ({baseline})"
                if passed
                else f"New lint errors introduced: {error_count} > baseline {baseline}"
            ),
            evidence={
                "errors": error_count,
                "baseline": baseline,
                "key_error_lines": output_lines[:6],
            },
            suggested_action="" if passed else "Remove newly introduced lint errors.",
        )


class HumanApprovalCheck:
    """Gate that requires explicit human approval."""

    check_type = "human_approval"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        approved = bool(getattr(spec, "approved", False)) or (
            context.task_id in context.human_approvals
            or spec.display_name() in context.human_approvals
        )
        return CheckResult(
            passed=approved,
            message="Human approval granted" if approved else "Awaiting human approval",
            evidence={"task_id": context.task_id, "approved": approved},
            suggested_action="" if approved else "Request human sign-off before marking done.",
        )


class LlmJudgeCheck:
    """Lowest-trust heuristic check using an optional command or callable hook."""

    check_type = "llm_judge"

    def run(self, spec: CheckSpec, context: CheckContext) -> CheckResult:
        if context.llm_judge_hook is not None:
            ok, reason = context.llm_judge_hook(spec, context.repo_root)
            return CheckResult(
                passed=ok,
                message=reason,
                evidence={"mode": "hook"},
                suggested_action="" if ok else "Address llm_judge feedback.",
            )

        cmd = getattr(spec, "command", None)
        if isinstance(cmd, str) and cmd.strip():
            code, stdout, stderr, _ = _run_shell(cmd, context.repo_root, spec.timeout_seconds)
            passed = code == 0
            return CheckResult(
                passed=passed,
                message="llm_judge command passed" if passed else "llm_judge command failed",
                evidence={
                    "mode": "command",
                    "stdout_tail": _tail(stdout),
                    "stderr_tail": _tail(stderr),
                },
                suggested_action="" if passed else "Address llm_judge feedback.",
            )

        return CheckResult(
            passed=False,
            message="No llm_judge hook or command configured",
            evidence={"mode": "unconfigured"},
            suggested_action="Configure an llm_judge command or hook.",
        )


def register_builtin_checks(registry: CheckRegistry) -> None:
    """Register all built-in DoneGate check handlers."""
    for handler in (
        CommandCheck(),
        TestSuiteCheck(),
        FileExistsCheck(),
        FileContainsCheck(),
        JsonPathCheck(),
        HttpCheck(),
        LintCleanCheck(),
        NoNewLintErrorsCheck(),
        HumanApprovalCheck(),
        LlmJudgeCheck(),
    ):
        registry.register(handler.check_type, handler)
