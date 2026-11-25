"""Language profiles and polyglot auto-detection for DoneGate."""

from __future__ import annotations

from donegate.profiles.loader import (
    DetectedProfile,
    detect_profiles,
    generate_contract,
    load_all_profiles,
)
from donegate.profiles.models import DefaultScopeSpec, LanguageProfile

__all__ = [
    "DefaultScopeSpec",
    "DetectedProfile",
    "LanguageProfile",
    "detect_profiles",
    "generate_contract",
    "load_all_profiles",
]
