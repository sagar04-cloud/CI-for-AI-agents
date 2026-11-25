"""Base types and plugin registry for DoneGate test output parsers."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Protocol

from pydantic import BaseModel, Field


class ParsedTestOutput(BaseModel):
    """Normalized test execution summary across any language/framework."""

    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    failing_test_names: list[str] = Field(default_factory=list)
    key_error_lines: list[str] = Field(default_factory=list)


class TestParser(Protocol):
    """Protocol for test output parsers."""

    name: str

    def parse(self, stdout: str, stderr: str, exit_code: int) -> ParsedTestOutput:
        """Parse test runner output into a normalized ParsedTestOutput."""
        ...


class ParserRegistry:
    """Registry of built-in and entry-point test parsers."""

    def __init__(self) -> None:
        self._parsers: dict[str, TestParser] = {}

    def register(self, name: str, parser: TestParser) -> None:
        """Register a parser under a given name."""
        self._parsers[name.lower()] = parser

    def get(self, name: str) -> TestParser:
        """Look up a parser by name, falling back to KeyError if unknown."""
        key = name.lower()
        if key not in self._parsers:
            available = ", ".join(sorted(self._parsers))
            raise KeyError(f"Unknown test parser {name!r}. Available: {available}")
        return self._parsers[key]

    def list_names(self) -> list[str]:
        """Return sorted list of registered parser names."""
        return sorted(self._parsers)

    def load_entry_points(self, group: str = "donegate.parsers") -> None:
        """Load third-party parsers from Python entry_points."""
        for ep in entry_points(group=group):
            loaded = ep.load()
            parser = loaded() if callable(loaded) and not hasattr(loaded, "parse") else loaded
            self.register(ep.name, parser)


_DEFAULT_REGISTRY: ParserRegistry | None = None


def get_parser_registry() -> ParserRegistry:
    """Return the global parser registry populated with built-ins and entry points."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        from donegate.parsers.builtins import register_builtin_parsers

        registry = ParserRegistry()
        register_builtin_parsers(registry)
        registry.load_entry_points()
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY
