"""Pydantic model for DoneGate language profiles."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DefaultScopeSpec(BaseModel):
    """Default source, test, and ignore globs for a language profile."""

    model_config = ConfigDict(extra="forbid")

    source: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    ignore: list[str] = Field(default_factory=list)


class LanguageProfile(BaseModel):
    """Language/toolchain profile loaded from YAML."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    display_name: str = ""
    detection_files: list[str] = Field(min_length=1)
    default_test_command: str = Field(min_length=1)
    test_parser: str = "generic"
    lint_command: str | None = None
    build_command: str | None = None
    typecheck_command: str | None = None
    default_scope: DefaultScopeSpec = Field(default_factory=DefaultScopeSpec)
    lockfiles: list[str] = Field(default_factory=list)
    tool_binaries: list[str] = Field(default_factory=list)
