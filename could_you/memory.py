import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import MemoryProps
from .cy_error import CYError, FaultOwner
from .logging_config import LOGGER
from .message import Message


class MemoryBackupError(CYError):
    def __init__(self, message: str):
        super().__init__(message=message, retriable=False, fault_owner=FaultOwner.USER)


def current_token_percent_used(messages: list[Message]) -> float | None:
    for message in reversed(messages):
        if not message.token_usage:
            continue

        percent_used = message.token_usage.percent_used()
        if percent_used is not None:
            return percent_used

    return None


def should_warn(percent_used: float | None, memory: MemoryProps) -> bool:
    if percent_used is None:
        return False

    return percent_used >= memory.warning_threshold_percent


def should_reject(percent_used: float | None, memory: MemoryProps) -> bool:
    if percent_used is None:
        return False

    return percent_used >= memory.rejection_threshold_percent


@dataclass(frozen=True)
class MemoryBackupResult:
    repo_path: Path
    backup_path: Path
    metadata_path: Path
    commit_message: str


def backup_dialogue(w_config_dir: Path, topic: str | None = None) -> MemoryBackupResult:
    """Back up workspace dialogue to a private, user-owned git repository."""
    w_config_dir = w_config_dir.resolve()
    dialogue_path = w_config_dir / "dialogue.json"

    if not dialogue_path.is_file():
        raise MemoryBackupError(f"No dialogue history found at {dialogue_path}")

    workspace_root = w_config_dir.parent.resolve()
    repo_path = _memory_repo_path(w_config_dir)
    workspace_key = _workspace_key(workspace_root)
    timestamp = _timestamp()
    backup_dir = repo_path / "workspaces" / workspace_key / "conversations"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_path, metadata_path = _backup_paths(backup_dir, timestamp)

    shutil.copy2(dialogue_path, backup_path)
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
    _git(repo_path, "add", *_backup_commit_paths(repo_path, w_config_dir, backup_path, metadata_path))
    _git(repo_path, "commit", "-m", commit_message)

    LOGGER.info(f"Backed up memory to {backup_path}")
    LOGGER.info(f"Committed memory backup in {repo_path}")

    return MemoryBackupResult(
        repo_path=repo_path,
        backup_path=backup_path,
        metadata_path=metadata_path,
        commit_message=commit_message,
    )


def _memory_repo_path(w_config_dir: Path) -> Path:
    configured_path = os.getenv("COULD_YOU_MEMORY_REPO")

    if configured_path:
        return Path(configured_path).expanduser().resolve()

    return w_config_dir.resolve()


def _backup_commit_paths(repo_path: Path, w_config_dir: Path, backup_path: Path, metadata_path: Path) -> list[str]:
    paths = [backup_path, metadata_path]

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


def _backup_paths(backup_dir: Path, timestamp: str) -> tuple[Path, Path]:
    suffix = 0

    while True:
        infix = timestamp if suffix == 0 else f"{timestamp}.{suffix}"
        backup_path = backup_dir / f"{infix}.dialogue.json"
        metadata_path = backup_dir / f"{infix}.metadata.json"

        if not backup_path.exists() and not metadata_path.exists():
            return backup_path, metadata_path

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
        raise MemoryBackupError("git is required to back up memories") from e

    return result.returncode == 0 and bool(result.stdout.strip())


def _commit_message(topic: str | None, timestamp: str) -> str:
    if topic:
        return f"memory: {topic}"

    return f"memory: backup {timestamp}"


def _git_executable() -> str:
    git_path = shutil.which("git")

    if not git_path:
        raise MemoryBackupError("git is required to back up memories")

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
        raise MemoryBackupError("git is required to back up memories") from e
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or str(e)).strip()
        raise MemoryBackupError(f"git {' '.join(args)} failed: {detail}") from e
