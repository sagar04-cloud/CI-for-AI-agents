"""Pluggable test output parsers for language-agnostic test_suite checks."""

from __future__ import annotations

from donegate.parsers.base import ParsedTestOutput, ParserRegistry, TestParser, get_parser_registry
from donegate.parsers.builtins import (
    CargoTestParser,
    GenericExitCodeParser,
    GoTestJsonParser,
    JestVitestParser,
    JUnitXmlParser,
    PytestParser,
    TapParser,
)

__all__ = [
    "CargoTestParser",
    "GenericExitCodeParser",
    "GoTestJsonParser",
    "JUnitXmlParser",
    "JestVitestParser",
    "ParsedTestOutput",
    "ParserRegistry",
    "PytestParser",
    "TapParser",
    "TestParser",
    "get_parser_registry",
]
