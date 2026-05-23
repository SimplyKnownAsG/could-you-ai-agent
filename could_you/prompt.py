"""
Utilities for processing and expanding prompt text, including COULD_YOU_LOAD_FILE directives safely.
"""

import getpass
import re
from pathlib import Path

from attrs import define, field

from .logging_config import LOGGER
from .metadata import LoadedFileMetadata, PromptMetadata

# Pattern to match COULD_YOU_LOAD_FILE(relative/path.md or glob)
COULD_YOU_LOAD_FILE_PATTERN = re.compile(r"^COULD_YOU_LOAD_FILE\((.+)\)$", re.MULTILINE)
COULD_YOU_DEFAULT_PROMPT_PATTERN = re.compile(r"^COULD_YOU_DEFAULT_PROMPT(\(\))?$", re.MULTILINE)

DEFAULT_PROMPT_TEMPLATE = """
Your name is {agent_name}.

COULD_YOU_LOAD_FILE(.could-you/SYSTEM_PROMPT.md)

COULD_YOU_LOAD_FILE(.could-you/FORMATIVE.md)

COULD_YOU_LOAD_FILE(.could-you/TODO.md)

COULD_YOU_LOAD_FILE(.could-you/MEMORY.md)

> NOTE for {agent_name}
>
> The Markdown files expanded below may not be formatted for your use. They may
> be out of date, and they may be completely incorrect.This default
> configuration automatically loads markdown files in the workspace root so
> fresh projects provide useful context. After you have intentional `.could-you`
> memory files, consider removing `COULD_YOU_LOAD_FILE(*.md)` from
> `.could-you/config.yaml` and loading only the files you explicitly want in the
> prompt.

COULD_YOU_LOAD_FILE(*.md)
"""


@define(frozen=True)
class PromptExpansionResult:
    text: str
    metadata: PromptMetadata = field(factory=PromptMetadata)


def enrich_raw_prompt(prompt: str) -> PromptExpansionResult:
    """
    Public entrypoint: applies all prompt enrichments to the raw prompt string.
    Add additional prompt-enriching logic here as needed.
    """
    prompt = _expand_cy_default_pattern(prompt)
    return _expand_cy_load_file(prompt)


def _expand_cy_default_pattern(prompt: str) -> str:
    return COULD_YOU_DEFAULT_PROMPT_PATTERN.sub(_default_prompt(), prompt)


def _default_prompt() -> str:
    return DEFAULT_PROMPT_TEMPLATE.format(agent_name=_default_agent_name())


def _default_agent_name() -> str:
    try:
        user = getpass.getuser()
    except OSError:
        user = "usr"

    user = user.strip() or "usr"
    return f"{user}-borg"


def _expand_cy_load_file(prompt: str) -> PromptExpansionResult:
    """
    Replace all COULD_YOU_LOAD_FILE(pattern) in the prompt with the actual contents of all files matching the glob pattern.
    """
    cwd = str(Path.cwd().resolve())
    loaded_files: list[LoadedFileMetadata] = []

    def _replace(match):
        rel_pattern = match.group(1).strip()
        expanded_paths = [Path(p) for p in sorted(Path().glob(rel_pattern))]
        result = ""

        for file_path in expanded_paths:
            if cwd not in str(file_path.resolve()):
                LOGGER.info(f"COULD_YOU_LOAD_FILE: Ignoring path: {file_path}")
                continue

            if not file_path.is_file():
                LOGGER.info(f"COULD_YOU_LOAD_FILE: Ignoring non-file path: {file_path}")
                continue

            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                loaded_files.append(LoadedFileMetadata.from_path(directive=rel_pattern, path=file_path))
                result += f'\n<could-you-prompt-expanded-file "{file_path.absolute()}">\n'
                result += content + "\n"
                result += f'</could-you-prompt-expanded-file "{file_path.absolute()}">\n\n'
            except Exception as e:
                LOGGER.warning(f"COULD_YOU_LOAD_FILE: Error loading {file_path.absolute()}: {e}")

        if not result:
            LOGGER.info(f"COULD_YOU_LOAD_FILE: No files matched pattern '{rel_pattern}'.")

        return result

    expanded_prompt = COULD_YOU_LOAD_FILE_PATTERN.sub(_replace, prompt)
    return PromptExpansionResult(text=expanded_prompt, metadata=PromptMetadata(loaded_files=loaded_files))
