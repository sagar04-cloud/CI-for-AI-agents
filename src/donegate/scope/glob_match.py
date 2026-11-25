"""Cross-platform glob matching with `**` and `{a,b}` brace support."""

from __future__ import annotations

import re
from functools import lru_cache


def _expand_braces(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]+)\}", pattern)
    if not match:
        return [pattern]
    prefix = pattern[: match.start()]
    suffix = pattern[match.end() :]
    results: list[str] = []
    for opt in match.group(1).split(","):
        results.extend(_expand_braces(f"{prefix}{opt}{suffix}"))
    return results


@lru_cache(maxsize=1024)
def _compile_single_glob(pattern: str) -> re.Pattern[str]:
    norm = pattern.replace("\\", "/").lstrip("./")
    i = 0
    n = len(norm)
    regex = ["^"]
    while i < n:
        if norm[i : i + 3] == "**/":
            regex.append("(?:.+/)?")
            i += 3
        elif norm[i : i + 2] == "**":
            regex.append(".*")
            i += 2
        elif norm[i] == "*":
            regex.append("[^/]*")
            i += 1
        elif norm[i] == "?":
            regex.append("[^/]")
            i += 1
        elif norm[i] == "[":
            j = i + 1
            if j < n and norm[j] in ("!", "^"):
                j += 1
            if j < n and norm[j] == "]":
                j += 1
            while j < n and norm[j] != "]":
                j += 1
            if j >= n:
                regex.append(re.escape("["))
                i += 1
            else:
                stuff = norm[i + 1 : j].replace("\\", "\\\\")
                if stuff.startswith("!"):
                    stuff = "^" + stuff[1:]
                regex.append(f"[{stuff}]")
                i = j + 1
        else:
            regex.append(re.escape(norm[i]))
            i += 1
    regex.append("$")
    return re.compile("".join(regex))


def match_glob(path: str, pattern: str) -> bool:
    """Match a POSIX-normalized relative path against a glob pattern."""
    norm_path = path.replace("\\", "/").lstrip("./")
    for expanded in _expand_braces(pattern):
        if _compile_single_glob(expanded).match(norm_path):
            return True
    return False
