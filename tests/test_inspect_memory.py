from pathlib import Path

from could_you.__main__ import create_parser
from could_you.config import Config, LLMProps, MemoryProps
from could_you.inspect_memory import dump_memory_inspection_yaml, inspect_memory_from_parts


def test_inspect_memory_reports_structured_data_and_yaml(tmp_path: Path):
    workspace_root = tmp_path / "project"
    w_config_dir = workspace_root / ".could-you"
    w_config_dir.mkdir(parents=True)

    (w_config_dir / "SYSTEM_PROMPT.md").write_text("system")
    (w_config_dir / "FORMATIVE.md").write_text("formative")
    (w_config_dir / "TODO.md").write_text("todo")
    (w_config_dir / "MEMORY.md").write_text("memory")
    (workspace_root / "README.md").write_text("readme")

    config = Config(
        llm=LLMProps(provider="openai"),
        systemPrompt="COULD_YOU_LOAD_FILE(.could-you/MEMORY.md)\nCOULD_YOU_LOAD_FILE(*.md)",
        memory=MemoryProps(warningThresholdPercent=50, rejectionThresholdPercent=75),
    )

    dialogue_path = w_config_dir / "dialogue.json"
    dialogue_path.write_text(
        "[\n"
        '  {"role": "user", "content": [{"text": "hi"}]},\n'
        '  {"role": "assistant", "content": [{"text": "hello"}], "metadata": {"totalTokens": 80, "tokenLimit": 100}}\n'
        "]\n"
    )

    archive_dir = w_config_dir / "workspaces" / "project-123" / "conversations"
    archive_dir.mkdir(parents=True)
    (archive_dir / "20260516T123456Z.dialogue.json").write_text("[]\n")
    (archive_dir / "20260516T123456Z.metadata.json").write_text('{"topic": "test"}\n')

    report = inspect_memory_from_parts(config=config, w_config_dir=w_config_dir)

    assert report.workspace == str(workspace_root.resolve())
    assert report.dialogue.exists is True
    assert report.dialogue.turns == 2
    assert report.dialogue.latest_token_percent_used == 80
    assert report.thresholds.warning_percent == 50
    assert report.thresholds.rejection_percent == 75
    assert report.prompt.loaded_bytes == len("memory") + len("readme")
    assert report.prompt.loaded_file_count == 2
    assert report.prompt.root_markdown_auto_load_enabled is True
    assert [Path(file.path).name for file in report.durable_files] == [
        "SYSTEM_PROMPT.md",
        "FORMATIVE.md",
        "TODO.md",
        "MEMORY.md",
    ]
    assert sorted(Path(file.path).name for file in report.archive.files) == [
        "20260516T123456Z.dialogue.json",
        "20260516T123456Z.metadata.json",
    ]
    assert report.archive.file_count == 2
    assert report.suggested_next_action == (
        "Dialogue is past the rejection threshold; compact or prune memory before the next normal run."
    )

    dumped = dump_memory_inspection_yaml(report)
    assert "workspace:" in dumped
    assert "dialogue:" in dumped
    assert "latestTokenPercentUsed: 80.0" in dumped
    assert "loadedFiles:" in dumped
    assert "rootMarkdownAutoLoadEnabled: true" in dumped
    assert "suggestedNextAction:" in dumped


def test_inspect_memory_yaml_suggests_root_autoload_when_no_token_pressure(tmp_path: Path):
    workspace_root = tmp_path / "project"
    w_config_dir = workspace_root / ".could-you"
    w_config_dir.mkdir(parents=True)
    (workspace_root / "README.md").write_text("readme")

    config = Config(
        llm=LLMProps(provider="openai"),
        systemPrompt="COULD_YOU_LOAD_FILE(*.md)",
    )

    report = inspect_memory_from_parts(config=config, w_config_dir=w_config_dir)
    dumped = dump_memory_inspection_yaml(report)

    assert "rootMarkdownAutoLoadEnabled: true" in dumped
    assert "suggestedNextAction:" in dumped
    assert "Root *.md auto-load is enabled; remove it if public docs are" in dumped
    assert "adding avoidable prompt weight." in dumped


def test_inspect_memory_cli_flags_parse():
    parser = create_parser()
    args = parser.parse_args(["--inspect-memory"])
    assert args.inspect_memory is True

    args = parser.parse_args(["--memory-status"])
    assert args.inspect_memory is True
