import json
from pathlib import Path

import pytest

from could_you.memory import MemoryBackupError, _backup_paths, backup_messages


def test_backup_messages_copies_history_and_metadata(tmp_path: Path, monkeypatch):
    workspace_root = tmp_path / "project"
    w_config_dir = workspace_root / ".could-you"
    memory_repo = tmp_path / "memories"
    w_config_dir.mkdir(parents=True)
    monkeypatch.setenv("COULD_YOU_MEMORY_REPO", str(memory_repo))
    monkeypatch.setattr("could_you.memory._timestamp", lambda: "20260516T123456Z")

    git_calls = []

    def fake_git(repo_path: Path, *args: str) -> None:
        git_calls.append((repo_path, args))
        if args == ("init",):
            (repo_path / ".git").mkdir()

    def fake_git_config_exists(_repo_path: Path, _key: str) -> bool:
        return False

    monkeypatch.setattr("could_you.memory._git", fake_git)
    monkeypatch.setattr("could_you.memory._git_config_exists", fake_git_config_exists)
    (w_config_dir / "messages.json").write_text('[{"role":"user"}]\n')

    result = backup_messages(w_config_dir, topic="private memory design")

    assert result.repo_path == memory_repo.resolve()
    assert result.backup_path.read_text() == '[{"role":"user"}]\n'
    assert result.commit_message == "memory: private memory design"

    metadata = json.loads(result.metadata_path.read_text())
    assert metadata == {
        "timestamp": "20260516T123456Z",
        "topic": "private memory design",
        "workspace": str(workspace_root.resolve()),
        "source": str(w_config_dir / "messages.json"),
    }

    assert git_calls == [
        (memory_repo.resolve(), ("init",)),
        (memory_repo.resolve(), ("config", "user.name", "could-you")),
        (memory_repo.resolve(), ("config", "user.email", "could-you@localhost")),
        (memory_repo.resolve(), ("add", str(result.backup_path), str(result.metadata_path))),
        (memory_repo.resolve(), ("commit", "-m", "memory: private memory design")),
    ]


def test_backup_paths_avoid_overwriting_existing_backup(tmp_path: Path):
    backup_dir = tmp_path / "conversations"
    backup_dir.mkdir()
    (backup_dir / "20260516T123456Z.messages.json").write_text("[]")

    backup_path, metadata_path = _backup_paths(backup_dir, "20260516T123456Z")

    assert backup_path == backup_dir / "20260516T123456Z.1.messages.json"
    assert metadata_path == backup_dir / "20260516T123456Z.1.metadata.json"


def test_backup_messages_requires_history(tmp_path: Path):
    w_config_dir = tmp_path / ".could-you"
    w_config_dir.mkdir()

    with pytest.raises(MemoryBackupError, match="No message history found"):
        backup_messages(w_config_dir)
