"""Smoke tests for DoneGate package setup."""

from donegate import __version__


def test_version_defined() -> None:
    assert __version__ == "1.1.0"
