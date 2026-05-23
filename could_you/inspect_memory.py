import os
from pathlib import Path

import yaml
from attrs import define, field
from cattrs import Converter

from .config import Config, load
from .dialogue import Dialogue
from .memory import current_token_percent_used
from .metadata import LoadedFileMetadata
from .prompt import enrich_raw_prompt

converter = Converter(use_alias=True)


@define(frozen=True)
class SizedPath:
    path: str
    bytes: int


@define(frozen=True)
class DialogueInspection:
    path: str
    exists: bool
    bytes: int
    turns: int
    latest_token_percent_used: float | None = field(default=None, alias="latestTokenPercentUsed")


@define(frozen=True)
class ThresholdInspection:
    warning_percent: float = field(alias="warningPercent")
    rejection_percent: float = field(alias="rejectionPercent")


@define(frozen=True)
class PromptInspection:
    loaded_files: list[LoadedFileMetadata] = field(factory=list, alias="loadedFiles")
    loaded_file_count: int = field(default=0, alias="loadedFileCount")
    loaded_bytes: int = field(default=0, alias="loadedBytes")
    root_markdown_auto_load_enabled: bool = field(default=False, alias="rootMarkdownAutoLoadEnabled")


@define(frozen=True)
class ArchiveInspection:
    files: list[SizedPath] = field(factory=list)
    file_count: int = field(default=0, alias="fileCount")
    bytes: int = 0


@define(frozen=True)
class MemoryInspection:
    workspace: str
    dialogue: DialogueInspection
    thresholds: ThresholdInspection
    prompt: PromptInspection
    suggested_next_action: str = field(alias="suggestedNextAction")
    durable_files: list[SizedPath] = field(factory=list, alias="durableFiles")
    archive: ArchiveInspection = field(factory=ArchiveInspection)


def inspect_memory(script_name: str | None = None) -> MemoryInspection:
    config, w_config_dir = load(script_name)
    return inspect_memory_from_parts(config=config, w_config_dir=w_config_dir)


def inspect_memory_from_parts(*, config: Config, w_config_dir: Path) -> MemoryInspection:
    workspace_root = w_config_dir.parent.resolve()
    dialogue_path = w_config_dir / "dialogue.json"
    archive_dir = w_config_dir / "workspaces"

    original_cwd = Path.cwd()
    try:
        if original_cwd != workspace_root:
            os.chdir(workspace_root)
        prompt_expansion = enrich_raw_prompt(config.system_prompt)
    finally:
        if Path.cwd() != original_cwd:
            os.chdir(original_cwd)

    dialogue_bytes = dialogue_path.stat().st_size if dialogue_path.is_file() else 0

    with Dialogue(w_config_dir, load=True, store=False) as dialogue:
        dialogue_turn_count = len(dialogue.messages)
        latest_token_percent_used = current_token_percent_used(dialogue.messages)

    prompt_loaded_files = prompt_expansion.metadata.loaded_files
    archive_files = _collect_sized_files(archive_dir, ["*.json"])

    report = MemoryInspection(
        workspace=str(workspace_root),
        dialogue=DialogueInspection(
            path=str(dialogue_path.resolve()),
            exists=dialogue_path.is_file(),
            bytes=dialogue_bytes,
            turns=dialogue_turn_count,
            latestTokenPercentUsed=latest_token_percent_used,
        ),
        thresholds=ThresholdInspection(
            warningPercent=config.memory.warning_threshold_percent,
            rejectionPercent=config.memory.rejection_threshold_percent,
        ),
        prompt=PromptInspection(
            loadedFiles=prompt_loaded_files,
            loadedFileCount=len(prompt_loaded_files),
            loadedBytes=sum(file.bytes for file in prompt_loaded_files),
            rootMarkdownAutoLoadEnabled=any(file.directive == "*.md" for file in prompt_loaded_files),
        ),
        durableFiles=_collect_durable_files(w_config_dir),
        archive=ArchiveInspection(
            files=archive_files,
            fileCount=len(archive_files),
            bytes=sum(file.bytes for file in archive_files),
        ),
        suggestedNextAction=_suggest_next_action(
            latest_token_percent_used=latest_token_percent_used,
            warning_threshold_percent=config.memory.warning_threshold_percent,
            rejection_threshold_percent=config.memory.rejection_threshold_percent,
            root_markdown_auto_load_enabled=any(file.directive == "*.md" for file in prompt_loaded_files),
            dialogue_bytes=dialogue_bytes,
            archive_bytes=sum(file.bytes for file in archive_files),
        ),
    )

    return report


def dump_memory_inspection_yaml(report: MemoryInspection) -> str:
    return yaml.safe_dump(converter.unstructure(report), sort_keys=False, default_flow_style=False)


def _suggest_next_action(
    *,
    latest_token_percent_used: float | None,
    warning_threshold_percent: float,
    rejection_threshold_percent: float,
    root_markdown_auto_load_enabled: bool,
    dialogue_bytes: int,
    archive_bytes: int,
) -> str:
    if latest_token_percent_used is not None:
        if latest_token_percent_used >= rejection_threshold_percent:
            return "Dialogue is past the rejection threshold; compact or prune memory before the next normal run."
        if latest_token_percent_used >= warning_threshold_percent:
            return "Dialogue is past the warning threshold; inspect and compact soon."

    if root_markdown_auto_load_enabled:
        return "Root *.md auto-load is enabled; remove it if public docs are adding avoidable prompt weight."

    if dialogue_bytes == 0:
        return "Dialogue is empty; no action needed yet."

    if archive_bytes == 0:
        return "Consider backing up dialogue before future pruning or compaction."

    return "Memory state looks healthy; continue with explicit memory lookup or gardening work."


def _collect_durable_files(w_config_dir: Path) -> list[SizedPath]:
    files = []
    for file_name in ("SYSTEM_PROMPT.md", "FORMATIVE.md", "TODO.md", "MEMORY.md"):
        path = w_config_dir / file_name
        if path.is_file():
            files.append(SizedPath(path=str(path.resolve()), bytes=path.stat().st_size))
    return files


def _collect_sized_files(root: Path, patterns: list[str]) -> list[SizedPath]:
    if not root.is_dir():
        return []

    seen: set[Path] = set()
    files: list[SizedPath] = []

    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            resolved_path = path.resolve()
            if not path.is_file() or resolved_path in seen:
                continue
            seen.add(resolved_path)
            files.append(SizedPath(path=str(resolved_path), bytes=resolved_path.stat().st_size))

    return files
