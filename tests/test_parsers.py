"""Tests for Phase 2 pluggable test output parsers."""

from __future__ import annotations

from donegate.parsers import get_parser_registry


def test_pytest_parser_pass_and_fail() -> None:
    parser = get_parser_registry().get("pytest")
    fail_out = """
============================= FAILURES =============================
FAILED tests/test_auth.py::test_expiry - AssertionError: expected True
E   AssertionError: assert False is True
1 failed, 4 passed, 1 skipped in 0.12s
"""
    res = parser.parse(fail_out, "", 1)
    assert res.passed == 4
    assert res.failed == 1
    assert res.skipped == 1
    assert res.failing_test_names == ["tests/test_auth.py::test_expiry"]
    assert any("AssertionError" in ln for ln in res.key_error_lines)


def test_jest_and_vitest_parser() -> None:
    reg = get_parser_registry()
    for name in ("jest", "vitest"):
        parser = reg.get(name)
        out = """
FAIL src/sum.test.ts
  ● adds numbers
    Expected: 4
    Received: 5
Tests: 1 failed, 3 passed, 1 skipped, 5 total
"""
        res = parser.parse(out, "", 1)
        assert res.failed == 1
        assert res.passed == 3
        assert res.skipped == 1
        assert len(res.failing_test_names) >= 1


def test_go_test_json_parser() -> None:
    parser = get_parser_registry().get("go_test")
    ndjson = "\n".join(
        [
            '{"Action":"run","Package":"pkg/auth","Test":"TestPass"}',
            '{"Action":"pass","Package":"pkg/auth","Test":"TestPass"}',
            '{"Action":"run","Package":"pkg/auth","Test":"TestFail"}',
            (
                '{"Action":"output","Package":"pkg/auth","Test":"TestFail",'
                '"Output":"auth_test.go:12: got 401\\n"}'
            ),
            '{"Action":"fail","Package":"pkg/auth","Test":"TestFail"}',
            '{"Action":"skip","Package":"pkg/auth","Test":"TestSkip"}',
        ]
    )
    res = parser.parse(ndjson, "", 1)
    assert res.passed == 1
    assert res.failed == 1
    assert res.skipped == 1
    assert res.failing_test_names == ["TestFail"]
    assert any("auth_test.go:12" in ln for ln in res.key_error_lines)


def test_cargo_test_parser() -> None:
    parser = get_parser_registry().get("cargo_test")
    out = """
running 3 tests
test math::add_works ... ok
test math::sub_works ... FAILED
test math::slow_test ... ignored

test result: FAILED. 1 passed; 1 failed; 1 ignored; 0 measured; 0 filtered out
"""
    res = parser.parse(out, "", 101)
    assert res.passed == 1
    assert res.failed == 1
    assert res.skipped == 1
    assert res.failing_test_names == ["math::sub_works"]


def test_junit_xml_parser() -> None:
    parser = get_parser_registry().get("junit_xml")
    xml_out = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="AppSuite" tests="3" failures="1" skipped="1">
  <testcase classname="com.example.AppTest" name="testOk" time="0.01"/>
  <testcase classname="com.example.AppTest" name="testBroken" time="0.02">
    <failure message="expected 200 but got 500">stacktrace</failure>
  </testcase>
  <testcase classname="com.example.AppTest" name="testSkipped" time="0.00">
    <skipped/>
  </testcase>
</testsuite>
"""
    res = parser.parse(xml_out, "", 1)
    assert res.passed == 1
    assert res.failed == 1
    assert res.skipped == 1
    assert res.failing_test_names == ["com.example.AppTest.testBroken"]
    assert any("expected 200" in ln for ln in res.key_error_lines)


def test_tap_parser() -> None:
    parser = get_parser_registry().get("tap")
    tap_out = """TAP version 13
1..3
ok 1 - loads config
not ok 2 - validates token
ok 3 - slow integration # SKIP no network
"""
    res = parser.parse(tap_out, "", 1)
    assert res.passed == 1
    assert res.failed == 1
    assert res.skipped == 1
    assert res.failing_test_names == ["validates token"]


def test_generic_parser() -> None:
    parser = get_parser_registry().get("generic")
    assert parser.parse("all good", "", 0).passed == 1
    fail = parser.parse("", "boom\nfatal", 1)
    assert fail.failed == 1
    assert "fatal" in fail.key_error_lines
