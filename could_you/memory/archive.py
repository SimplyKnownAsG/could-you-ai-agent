import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..cy_error import CYError, FaultOwner
from ..logging_config import LOGGER


class MemoryArchiveError(CYError):
    def __init__(self, message: str):
        super().__init__(message=message, retriable=False, fault_owner=FaultOwner.USER)


@dataclass(frozen=True)
class MemoryArchiveResult:
    repo_path: Path
    archive_path: Path
    metadata_path: Path
    commit_message: str


def archive_dialogue(w_config_dir: Path, topic: str | None = None) -> MemoryArchiveResult:
    """Back up workspace dialogue to a private, user-owned git repository."""
    w_config_dir = w_config_dir.resolve()
    dialogue_path = w_config_dir / "dialogue.json"

    if not dialogue_path.is_file():
        raise MemoryArchiveError(f"No dialogue history found at {dialogue_path}")

    workspace_root = w_config_dir.parent.resolve()
    repo_path = _memory_repo_path(w_config_dir)
    workspace_key = _workspace_key(workspace_root)
    timestamp = _timestamp()
    archive_dir = repo_path / "workspaces" / workspace_key / "conversations"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_path, metadata_path = _archive_paths(archive_dir, timestamp)

    shutil.copy2(dialogue_path, archive_path)
    metadata_path.write_text(
        json.dumps(
            {
                "timestamp": timestamp,
                "topic": topic,
                "workspace": str(workspace_root),
                "source": str(dialogue_path),
            },
            indent=2,
        )
        + "\n"
    )

    _ensure_git_repo(repo_path)
    _ensure_git_identity(repo_path)

    commit_message = _commit_message(topic, timestamp)
    _git(repo_path, "add", *_archive_commit_paths(repo_path, w_config_dir, archive_path, metadata_path))
    _git(repo_path, "commit", "-m", commit_message)

    LOGGER.info(f"Backed up memory to {archive_path}")
    LOGGER.info(f"Committed memory archive in {repo_path}")

    return MemoryArchiveResult(
        repo_path=repo_path,
        archive_path=archive_path,
        metadata_path=metadata_path,
        commit_message=commit_message,
    )


def _memory_repo_path(w_config_dir: Path) -> Path:
    configured_path = os.getenv("COULD_YOU_MEMORY_REPO")

    if configured_path:
        return Path(configured_path).expanduser().resolve()

    return w_config_dir.resolve()


def _archive_commit_paths(repo_path: Path, w_config_dir: Path, archive_path: Path, metadata_path: Path) -> list[str]:
    paths = [archive_path, metadata_path]

    for file_name in (
        "config.yaml",
        "config.yml",
        "config.json",
        "SYSTEM_PROMPT.md",
        "FORMATIVE.md",
        "TODO.md",
        "MEMORY.md",
    ):
        path = w_config_dir / file_name

        if path.is_file() and path.is_relative_to(repo_path):
            paths.append(path)

    return [str(path) for path in paths]


def _workspace_key(workspace_root: Path) -> str:
    digest = hashlib.sha256(str(workspace_root).encode()).hexdigest()[:12]
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in workspace_root.name)
    return f"{safe_name}-{digest}"


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _archive_paths(archive_dir: Path, timestamp: str) -> tuple[Path, Path]:
    suffix = 0

    while True:
        infix = timestamp if suffix == 0 else f"{timestamp}.{suffix}"
        archive_path = archive_dir / f"{infix}.dialogue.json"
        metadata_path = archive_dir / f"{infix}.metadata.json"

        if not archive_path.exists() and not metadata_path.exists():
            return archive_path, metadata_path

        suffix += 1


def _ensure_git_repo(repo_path: Path) -> None:
    repo_path.mkdir(parents=True, exist_ok=True)

    if not (repo_path / ".git").exists():
        _git(repo_path, "init")


def _ensure_git_identity(repo_path: Path) -> None:
    if not _git_config_exists(repo_path, "user.name"):
        _git(repo_path, "config", "user.name", "could-you")

    if not _git_config_exists(repo_path, "user.email"):
        _git(repo_path, "config", "user.email", "could-you@localhost")


def _git_config_exists(repo_path: Path, key: str) -> bool:
    try:
        result = subprocess.run(
            [_git_executable(), "-C", str(repo_path), "config", "--get", key],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise MemoryArchiveError("git is required to back up memories") from e

    return result.returncode == 0 and bool(result.stdout.strip())


def _commit_message(topic: str | None, timestamp: str) -> str:
    if topic:
        return f"memory: {topic}"

    return f"memory: archive {timestamp}"


def _git_executable() -> str:
    git_path = shutil.which("git")

    if not git_path:
        raise MemoryArchiveError("git is required to back up memories")

    return git_path


def _git(repo_path: Path, *args: str) -> None:
    try:
        subprocess.run(
            [_git_executable(), "-C", str(repo_path), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise MemoryArchiveError("git is required to back up memories") from e
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or str(e)).strip()
        raise MemoryArchiveError(f"git {' '.join(args)} failed: {detail}") from e
