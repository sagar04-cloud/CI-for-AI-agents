"""Git baseline snapshot and diff-based scope enforcement."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from donegate.contract.models import ScopeMode, ScopeSpec
from donegate.profiles.loader import load_all_profiles
from donegate.scope.glob_match import match_glob

DEFAULT_LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "Cargo.lock",
    "go.sum",
    "poetry.lock",
    "uv.lock",
    "Pipfile.lock",
    "composer.lock",
    "Gemfile.lock",
    "packages.lock.json",
    "gradle.lockfile",
    "skills-lock.json",
}

ALWAYS_IGNORED_GLOBS = [
    ".donegate/**",
    ".git/**",
    ".agents/**",
    "**/__pycache__/**",
    "**/*.pyc",
]


class ChangedFile(BaseModel):
    """A file changed since the task baseline."""

    path: str
    status: str  # M, A, D, R, U
    old_path: str | None = None


class GitBaseline(BaseModel):
    """Snapshot of repository state when a task started."""

    head_sha: str | None = None
    preexisting_hashes: dict[str, str] = Field(default_factory=dict)


class ScopeCheckResult(BaseModel):
    """Outcome of checking changed files against a task's ScopeSpec."""

    passed: bool
    mode: ScopeMode
    changed_files: list[ChangedFile] = Field(default_factory=list)
    ignored_files: list[str] = Field(default_factory=list)
    out_of_scope_files: list[str] = Field(default_factory=list)
    revert_commands: list[str] = Field(default_factory=list)
    message: str = ""


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        check=False,
    )


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return "<missing>"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_porcelain_z(raw: bytes) -> list[ChangedFile]:
    """Parse `git status --porcelain=v1 -z -uall` output safely across platforms."""
    if not raw:
        return []
    entries = raw.split(b"\x00")
    changed: list[ChangedFile] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        if not entry:
            i += 1
            continue
        text = entry.decode("utf-8", errors="replace")
        if len(text) < 4:
            i += 1
            continue
        xy = text[:2]
        path = text[3:].replace("\\", "/")
        if xy == "??":
            changed.append(ChangedFile(path=path, status="U"))
            i += 1
        elif "R" in xy or "C" in xy:
            new_path = path
            old_path: str | None = None
            if i + 1 < len(entries) and entries[i + 1]:
                old_path = entries[i + 1].decode("utf-8", errors="replace").replace("\\", "/")
                i += 2
            else:
                i += 1
            changed.append(ChangedFile(path=new_path, status="R", old_path=old_path))
        elif "D" in xy:
            changed.append(ChangedFile(path=path, status="D"))
            i += 1
        elif "A" in xy:
            changed.append(ChangedFile(path=path, status="A"))
            i += 1
        else:
            changed.append(ChangedFile(path=path, status="M"))
            i += 1
    return changed


def snapshot_baseline(repo_root: Path) -> GitBaseline:
    """Capture current HEAD SHA and hashes of any pre-existing dirty/untracked files."""
    head_proc = _run_git(repo_root, ["rev-parse", "HEAD"])
    head_sha = (
        head_proc.stdout.decode("utf-8", errors="replace").strip()
        if head_proc.returncode == 0
        else None
    )
    status_proc = _run_git(repo_root, ["status", "--porcelain=v1", "-z", "-uall"])
    hashes: dict[str, str] = {}
    if status_proc.returncode == 0:
        for item in _parse_porcelain_z(status_proc.stdout):
            hashes[item.path] = _file_sha256(repo_root / item.path)
    return GitBaseline(head_sha=head_sha, preexisting_hashes=hashes)


def _collect_changes(repo_root: Path, baseline: GitBaseline | None) -> list[ChangedFile]:
    """Collect working-tree and committed changes since baseline."""
    changes_by_path: dict[str, ChangedFile] = {}

    if baseline and baseline.head_sha:
        diff_proc = _run_git(
            repo_root, ["diff", "--name-status", "-z", "-M", baseline.head_sha, "HEAD"]
        )
        if diff_proc.returncode == 0 and diff_proc.stdout:
            tokens = [
                t.decode("utf-8", errors="replace")
                for t in diff_proc.stdout.split(b"\x00")
                if t
            ]
            i = 0
            while i < len(tokens):
                code = tokens[i]
                if code.startswith("R") and i + 2 < len(tokens):
                    old_p = tokens[i + 1].replace("\\", "/")
                    new_p = tokens[i + 2].replace("\\", "/")
                    changes_by_path[new_p] = ChangedFile(path=new_p, status="R", old_path=old_p)
                    i += 3
                elif i + 1 < len(tokens):
                    p = tokens[i + 1].replace("\\", "/")
                    changes_by_path[p] = ChangedFile(path=p, status=code[:1])
                    i += 2
                else:
                    i += 1

    status_proc = _run_git(repo_root, ["status", "--porcelain=v1", "-z", "-uall"])
    if status_proc.returncode == 0:
        for item in _parse_porcelain_z(status_proc.stdout):
            if (
                baseline
                and item.path in baseline.preexisting_hashes
                and _file_sha256(repo_root / item.path) == baseline.preexisting_hashes[item.path]
            ):
                continue
            changes_by_path[item.path] = item

    return list(changes_by_path.values())


def _auto_ignore_globs(
    repo_root: Path, active_profiles: list[str] | None
) -> tuple[list[str], set[str]]:
    ignore_globs = list(ALWAYS_IGNORED_GLOBS)
    lockfiles = set(DEFAULT_LOCKFILES)
    profiles = load_all_profiles(repo_root)
    names = active_profiles or list(profiles.keys())
    for name in names:
        prof = profiles.get(name.lower())
        if prof is not None:
            ignore_globs.extend(prof.default_scope.ignore)
            lockfiles.update(prof.lockfiles)
    return ignore_globs, lockfiles


def _is_ignored(
    path: str,
    scope: ScopeSpec,
    ignore_globs: list[str],
    lockfiles: set[str],
) -> bool:
    if any(match_glob(path, d) for d in scope.deny):
        return False
    basename = path.rsplit("/", 1)[-1]
    if scope.ignore_lockfiles and basename in lockfiles:
        return True
    return any(match_glob(path, g) for g in ignore_globs)


def _is_allowed(path: str, scope: ScopeSpec) -> bool:
    if any(match_glob(path, d) for d in scope.deny):
        return False
    return any(match_glob(path, a) for a in scope.allow)


def check_scope(
    repo_root: Path,
    scope: ScopeSpec,
    mode: ScopeMode = ScopeMode.BLOCK,
    baseline: GitBaseline | None = None,
    active_profiles: list[str] | None = None,
) -> ScopeCheckResult:
    """Evaluate changed files against allow/deny globs and return ScopeCheckResult."""
    changed = _collect_changes(repo_root, baseline)
    ignore_globs, lockfiles = _auto_ignore_globs(repo_root, active_profiles)

    ignored: list[str] = []
    offending: list[str] = []
    revert_cmds: list[str] = []

    for item in changed:
        if _is_ignored(item.path, scope, ignore_globs, lockfiles):
            ignored.append(item.path)
            continue

        paths_to_check = [item.path]
        if item.old_path:
            paths_to_check.append(item.old_path)

        if not all(_is_allowed(p, scope) for p in paths_to_check):
            offending.append(item.path)
            if item.status == "U":
                revert_cmds.append(f'git clean -f -- "{item.path}"')
            elif item.status == "R" and item.old_path:
                revert_cmds.append(
                    f'git restore --staged --worktree -- "{item.old_path}" "{item.path}"'
                )
            else:
                revert_cmds.append(f'git restore -- "{item.path}"')

    if not offending:
        return ScopeCheckResult(
            passed=True,
            mode=mode,
            changed_files=changed,
            ignored_files=ignored,
            message="All changes are within allowed scope.",
        )

    passed = mode != ScopeMode.BLOCK
    msg = (
        f"Scope violation ({mode.value}): {len(offending)} out-of-scope file(s): "
        f"{', '.join(offending[:5])}"
    )
    return ScopeCheckResult(
        passed=passed,
        mode=mode,
        changed_files=changed,
        ignored_files=ignored,
        out_of_scope_files=offending,
        revert_commands=revert_cmds,
        message=msg,
    )
