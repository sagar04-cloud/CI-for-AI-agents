"""Built-in test output parsers: pytest, jest/vitest, go test, cargo, JUnit XML, TAP, generic."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

from donegate.parsers.base import ParsedTestOutput, ParserRegistry


def _tail_lines(text: str, limit: int = 8) -> list[str]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return lines[-limit:]


class PytestParser:
    """Parser for pytest stdout/stderr."""

    name = "pytest"

    _SUMMARY_RE = re.compile(
        r"(?:(?P<failed>\d+)\s+failed)?[,\s]*"
        r"(?:(?P<passed>\d+)\s+passed)?[,\s]*"
        r"(?:(?P<skipped>\d+)\s+skipped)?[,\s]*"
        r"(?:(?P<errors>\d+)\s+error)?"
    )
    _FAILED_LINE_RE = re.compile(r"^FAILED\s+([^\s]+(?:\s+-\s+.*)?)$")

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParsedTestOutput:
        combined = f"{stdout}\n{stderr}"
        passed = failed = skipped = 0
        failing_names: list[str] = []
        error_lines: list[str] = []

        for raw in combined.splitlines():
            line = raw.strip()
            m_fail = self._FAILED_LINE_RE.match(line)
            if m_fail:
                name = m_fail.group(1).split(" - ", 1)[0].strip()
                if name not in failing_names:
                    failing_names.append(name)
                error_lines.append(line)
            elif line.startswith("E   "):
                error_lines.append(line)

        for raw in reversed(combined.splitlines()):
            if "passed" in raw or "failed" in raw or "error" in raw or "skipped" in raw:
                if m := re.search(r"(\d+)\s+passed", raw):
                    passed = int(m.group(1))
                if m := re.search(r"(\d+)\s+failed", raw):
                    failed = int(m.group(1))
                if m := re.search(r"(\d+)\s+errors?", raw):
                    failed += int(m.group(1))
                if m := re.search(r"(\d+)\s+skipped", raw):
                    skipped = int(m.group(1))
                if passed or failed or skipped:
                    break

        if exit_code != 0 and failed == 0:
            failed = max(1, len(failing_names))
        if not error_lines and exit_code != 0:
            error_lines = _tail_lines(combined, limit=6)

        return ParsedTestOutput(
            passed=passed,
            failed=failed,
            skipped=skipped,
            failing_test_names=failing_names,
            key_error_lines=error_lines[:8],
        )


class JestVitestParser:
    """Parser for Jest and Vitest text output."""

    name = "jest"

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParsedTestOutput:
        combined = f"{stdout}\n{stderr}"
        passed = failed = skipped = 0
        failing_names: list[str] = []
        error_lines: list[str] = []

        for raw in combined.splitlines():
            line = raw.strip()
            if line.startswith("Tests:"):
                if m := re.search(r"(\d+)\s+failed", line):
                    failed = int(m.group(1))
                if m := re.search(r"(\d+)\s+passed", line):
                    passed = int(m.group(1))
                if m := re.search(r"(\d+)\s+skipped", line):
                    skipped = int(m.group(1))
            elif line.startswith(("● ", "FAIL ", "× ")):
                name = line.lstrip("●× ").strip()
                if name and name not in failing_names:
                    failing_names.append(name)
                error_lines.append(line)
            elif "Expected:" in line or "Received:" in line or "AssertionError" in line:
                error_lines.append(line)

        if exit_code != 0 and failed == 0:
            failed = max(1, len(failing_names))
        if not error_lines and exit_code != 0:
            error_lines = _tail_lines(combined, limit=6)

        return ParsedTestOutput(
            passed=passed,
            failed=failed,
            skipped=skipped,
            failing_test_names=failing_names,
            key_error_lines=error_lines[:8],
        )


class GoTestJsonParser:
    """Parser for `go test -json` NDJSON event stream."""

    name = "go_test"

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParsedTestOutput:
        passed = failed = skipped = 0
        failing_names: list[str] = []
        error_lines: list[str] = []

        for raw in stdout.splitlines():
            line = raw.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            action = event.get("Action")
            test_name = event.get("Test")
            if test_name:
                if action == "pass":
                    passed += 1
                elif action == "fail":
                    failed += 1
                    if test_name not in failing_names:
                        failing_names.append(test_name)
                elif action == "skip":
                    skipped += 1
            if action == "output":
                out = str(event.get("Output", "")).strip()
                if out and ("FAIL" in out or "_test.go:" in out or "Error" in out):
                    error_lines.append(out)

        if exit_code != 0 and failed == 0:
            failed = max(1, len(failing_names))
        if not error_lines and exit_code != 0:
            error_lines = _tail_lines(f"{stdout}\n{stderr}", limit=6)

        return ParsedTestOutput(
            passed=passed,
            failed=failed,
            skipped=skipped,
            failing_test_names=failing_names,
            key_error_lines=error_lines[:8],
        )


class CargoTestParser:
    """Parser for Rust `cargo test` output."""

    name = "cargo_test"

    _RESULT_RE = re.compile(
        r"test result:\s+\w+\.\s+(\d+)\s+passed;\s+(\d+)\s+failed;\s+(\d+)\s+ignored"
    )
    _TEST_LINE_RE = re.compile(r"^test\s+([^\s]+)\s+\.\.\.\s+FAILED$")

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParsedTestOutput:
        combined = f"{stdout}\n{stderr}"
        passed = failed = skipped = 0
        failing_names: list[str] = []
        error_lines: list[str] = []

        for raw in combined.splitlines():
            line = raw.strip()
            if m_test := self._TEST_LINE_RE.match(line):
                name = m_test.group(1)
                if name not in failing_names:
                    failing_names.append(name)
                error_lines.append(line)
            elif m_res := self._RESULT_RE.search(line):
                passed += int(m_res.group(1))
                failed += int(m_res.group(2))
                skipped += int(m_res.group(3))
            elif "panicked at" in line or "assertion" in line.lower():
                error_lines.append(line)

        if exit_code != 0 and failed == 0:
            failed = max(1, len(failing_names))
        if not error_lines and exit_code != 0:
            error_lines = _tail_lines(combined, limit=6)

        return ParsedTestOutput(
            passed=passed,
            failed=failed,
            skipped=skipped,
            failing_test_names=failing_names,
            key_error_lines=error_lines[:8],
        )


class JUnitXmlParser:
    """Parser for JUnit XML output (Java/Kotlin, .NET, PHPUnit, pytest --junitxml, etc.)."""

    name = "junit_xml"

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParsedTestOutput:
        xml_text = stdout.strip()
        if not xml_text.startswith("<"):
            # Try to find XML fragment inside stdout
            idx = xml_text.find("<testsuite")
            if idx == -1:
                idx = xml_text.find("<testsuites")
            if idx != -1:
                xml_text = xml_text[idx:]

        passed = failed = skipped = 0
        failing_names: list[str] = []
        error_lines: list[str] = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return GenericExitCodeParser().parse(stdout, stderr, exit_code)

        suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
        for suite in suites:
            for case in suite.findall("testcase"):
                name = case.attrib.get("name", "unknown")
                classname = case.attrib.get("classname", "")
                full_name = f"{classname}.{name}" if classname else name
                failure = case.find("failure")
                error = case.find("error")
                skip = case.find("skipped")
                if failure is not None or error is not None:
                    failed += 1
                    failing_names.append(full_name)
                    node = failure if failure is not None else error
                    msg = node.attrib.get("message", "") if node is not None else ""
                    if msg:
                        error_lines.append(f"{full_name}: {msg}")
                    elif node is not None and node.text:
                        first = node.text.strip().splitlines()[0]
                        error_lines.append(f"{full_name}: {first}")
                elif skip is not None:
                    skipped += 1
                else:
                    passed += 1

        if exit_code != 0 and failed == 0:
            failed = max(1, len(failing_names))

        return ParsedTestOutput(
            passed=passed,
            failed=failed,
            skipped=skipped,
            failing_test_names=failing_names,
            key_error_lines=error_lines[:8],
        )


class TapParser:
    """Parser for Test Anything Protocol (TAP) v12/v13/v14 output."""

    name = "tap"

    _LINE_RE = re.compile(r"^(ok|not ok)\s+(\d+)?\s*-?\s*(.*)$")

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParsedTestOutput:
        passed = failed = skipped = 0
        failing_names: list[str] = []
        error_lines: list[str] = []

        for raw in stdout.splitlines():
            line = raw.strip()
            m = self._LINE_RE.match(line)
            if not m:
                continue
            status, num, desc = m.group(1), m.group(2) or "?", m.group(3).strip()
            upper = desc.upper()
            if "# SKIP" in upper or "# TODO" in upper:
                skipped += 1
            elif status == "ok":
                passed += 1
            else:
                failed += 1
                label = desc or f"test #{num}"
                failing_names.append(label)
                error_lines.append(line)

        if exit_code != 0 and failed == 0:
            failed = max(1, len(failing_names))
        if not error_lines and exit_code != 0:
            error_lines = _tail_lines(f"{stdout}\n{stderr}", limit=6)

        return ParsedTestOutput(
            passed=passed,
            failed=failed,
            skipped=skipped,
            failing_test_names=failing_names,
            key_error_lines=error_lines[:8],
        )


class GenericExitCodeParser:
    """Fallback parser relying on process exit code and output tail."""

    name = "generic"

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParsedTestOutput:
        combined = f"{stdout}\n{stderr}"
        if exit_code == 0:
            return ParsedTestOutput(passed=1, failed=0, skipped=0)
        return ParsedTestOutput(
            passed=0,
            failed=1,
            skipped=0,
            failing_test_names=["command"],
            key_error_lines=_tail_lines(combined, limit=6),
        )


def register_builtin_parsers(registry: ParserRegistry) -> None:
    """Register all built-in DoneGate test parsers."""
    registry.register("pytest", PytestParser())
    jest_parser = JestVitestParser()
    registry.register("jest", jest_parser)
    registry.register("vitest", jest_parser)
    registry.register("go_test", GoTestJsonParser())
    registry.register("cargo_test", CargoTestParser())
    registry.register("junit_xml", JUnitXmlParser())
    registry.register("tap", TapParser())
    registry.register("generic", GenericExitCodeParser())
