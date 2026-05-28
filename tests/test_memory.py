import json
from pathlib import Path

import pytest

from could_you.config import MemoryProps
from could_you.memory.backup import (
    MemoryBackupError,
    _backup_commit_paths,
    _backup_paths,
    backup_dialogue,
)
from could_you.memory.tokens import (
    current_token_percent_used,
    should_reject,
    should_warn,
)
from could_you.message import Message, TextContent, TokenUsage


def test_backup_dialogue_copies_history_and_metadata(tmp_path: Path, monkeypatch):
    workspace_root = tmp_path / "project"
    w_config_dir = workspace_root / ".could-you"
    memory_repo = tmp_path / "memories"
    w_config_dir.mkdir(parents=True)
    monkeypatch.setenv("COULD_YOU_MEMORY_REPO", str(memory_repo))
    monkeypatch.setattr("could_you.memory.backup._timestamp", lambda: "20260516T123456Z")

    git_calls = []

    def fake_git(repo_path: Path, *args: str) -> None:
        git_calls.append((repo_path, args))
        if args == ("init",):
            (repo_path / ".git").mkdir()

    def fake_git_config_exists(_repo_path: Path, _key: str) -> bool:
        return False

    monkeypatch.setattr("could_you.memory.backup._git", fake_git)
    monkeypatch.setattr("could_you.memory.backup._git_config_exists", fake_git_config_exists)
    (w_config_dir / "dialogue.json").write_text('[{"role":"user"}]\n')

    result = backup_dialogue(w_config_dir, topic="private memory design")

    assert result.repo_path == memory_repo.resolve()
    assert result.backup_path.read_text() == '[{"role":"user"}]\n'
    assert result.commit_message == "memory: private memory design"

    metadata = json.loads(result.metadata_path.read_text())
    assert metadata == {
        "timestamp": "20260516T123456Z",
        "topic": "private memory design",
        "workspace": str(workspace_root.resolve()),
        "source": str(w_config_dir / "dialogue.json"),
    }

    assert git_calls == [
        (memory_repo.resolve(), ("init",)),
        (memory_repo.resolve(), ("config", "user.name", "could-you")),
        (memory_repo.resolve(), ("config", "user.email", "could-you@localhost")),
        (memory_repo.resolve(), ("add", str(result.backup_path), str(result.metadata_path))),
        (memory_repo.resolve(), ("commit", "-m", "memory: private memory design")),
    ]


def test_backup_dialogue_defaults_to_workspace_config_dir(tmp_path: Path, monkeypatch):
    workspace_root = tmp_path / "project"
    w_config_dir = workspace_root / ".could-you"
    w_config_dir.mkdir(parents=True)
    monkeypatch.delenv("COULD_YOU_MEMORY_REPO", raising=False)
    monkeypatch.setattr("could_you.memory.backup._timestamp", lambda: "20260516T123456Z")

    def fake_git(_repo_path: Path, *_args: str) -> None:
        pass

    def fake_git_config_exists(_repo_path: Path, _key: str) -> bool:
        return True

    monkeypatch.setattr("could_you.memory.backup._git", fake_git)
    monkeypatch.setattr("could_you.memory.backup._git_config_exists", fake_git_config_exists)
    (w_config_dir / "dialogue.json").write_text('[{"role":"user"}]\n')

    result = backup_dialogue(w_config_dir)

    assert result.repo_path == w_config_dir.resolve()
    assert result.backup_path.is_file()


def test_backup_commit_paths_include_prompt_and_memory_files_in_same_repo(tmp_path: Path):
    w_config_dir = tmp_path / ".could-you"
    w_config_dir.mkdir()
    backup_path = w_config_dir / "workspaces" / "project-123" / "conversations" / "backup.dialogue.json"
    metadata_path = backup_path.with_name("backup.metadata.json")
    backup_path.parent.mkdir(parents=True)
    backup_path.write_text("[]")
    metadata_path.write_text("{}")
    (w_config_dir / "config.yaml").write_text("systemPrompt: hi\n")
    (w_config_dir / "SYSTEM_PROMPT.md").write_text("# System\n")
    (w_config_dir / "FORMATIVE.md").write_text("# Formative\n")
    (w_config_dir / "TODO.md").write_text("# TODO\n")
    (w_config_dir / "MEMORY.md").write_text("# Memory\n")

    paths = _backup_commit_paths(w_config_dir, w_config_dir, backup_path, metadata_path)

    assert paths == [
        str(backup_path),
        str(metadata_path),
        str(w_config_dir / "config.yaml"),
        str(w_config_dir / "SYSTEM_PROMPT.md"),
        str(w_config_dir / "FORMATIVE.md"),
        str(w_config_dir / "TODO.md"),
        str(w_config_dir / "MEMORY.md"),
    ]


def test_backup_paths_avoid_overwriting_existing_backup(tmp_path: Path):
    backup_dir = tmp_path / "conversations"
    backup_dir.mkdir()
    (backup_dir / "20260516T123456Z.dialogue.json").write_text("[]")

    backup_path, metadata_path = _backup_paths(backup_dir, "20260516T123456Z")

    assert backup_path == backup_dir / "20260516T123456Z.1.dialogue.json"
    assert metadata_path == backup_dir / "20260516T123456Z.1.metadata.json"


def test_backup_dialogue_requires_history(tmp_path: Path):
    w_config_dir = tmp_path / ".could-you"
    w_config_dir.mkdir()

    with pytest.raises(MemoryBackupError, match="No dialogue history found"):
        backup_dialogue(w_config_dir)


def test_current_token_percent_used_reads_latest_message_with_usage():
    messages = [
        Message(
            role="assistant", content=[TextContent(text="old")], tokenUsage=TokenUsage(totalTokens=10, tokenLimit=100)
        ),
        Message(role="user", content=[TextContent(text="hi")]),
        Message(
            role="assistant", content=[TextContent(text="new")], tokenUsage=TokenUsage(totalTokens=80, tokenLimit=100)
        ),
    ]

    assert current_token_percent_used(messages) == 80


def test_current_token_percent_used_returns_none_without_complete_usage():
    messages = [
        Message(role="assistant", content=[TextContent(text="missing")], tokenUsage=TokenUsage(totalTokens=80)),
        Message(role="user", content=[TextContent(text="hi")]),
    ]

    assert current_token_percent_used(messages) is None


def test_memory_pressure_thresholds():
    memory = MemoryProps(warningThresholdPercent=75, rejectionThresholdPercent=90)

    assert not should_warn(None, memory)
    assert not should_warn(74.9, memory)
    assert should_warn(75, memory)
    assert should_warn(90, memory)

    assert not should_reject(None, memory)
    assert not should_reject(89.9, memory)
    assert should_reject(90, memory)
