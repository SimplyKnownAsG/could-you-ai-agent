"""
Utilities for processing and expanding prompt text, including COULD_YOU_LOAD_FILE directives safely.
"""

import re
from pathlib import Path

from .logging_config import LOGGER

# Pattern to match COULD_YOU_LOAD_FILE(relative/path.md or glob)
COULD_YOU_LOAD_FILE_PATTERN = re.compile(r"^COULD_YOU_LOAD_FILE\((.+)\)$", re.MULTILINE)
COULD_YOU_DEFAULT_PROMPT_PATTERN = re.compile(r"^COULD_YOU_DEFAULT_PROMPT(\(\))?$", re.MULTILINE)

DEFAULT_PROMPT = """
Your name is Cy.

You are an agent responsible for helping a software developer perform tasks.

DO ASSUME file content is correct.

DO NOT ASSUME any file edits you have previously made will be persisted, or were correct.

DO NOT ASSUME that you should make file edits, only make file changes if asked. For example, if asked to \"show\" or
\"tell\" only provide an answer.

COULD_YOU_LOAD_FILE(*.md)
"""


def enrich_raw_prompt(prompt: str) -> str:
    """
    Public entrypoint: applies all prompt enrichments to the raw prompt string.
    Add additional prompt-enriching logic here as needed.
    """
    prompt = _expand_cy_default_pattern(prompt)
    return _expand_cy_load_file(prompt)


def _expand_cy_default_pattern(prompt: str) -> str:
    return COULD_YOU_DEFAULT_PROMPT_PATTERN.sub(DEFAULT_PROMPT, prompt)


def _expand_cy_load_file(prompt: str) -> str:
    """
    Replace all COULD_YOU_LOAD_FILE(pattern) in the prompt with the actual contents of all files matching the glob pattern.
    """
    cwd = str(Path.cwd().resolve())

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
                result += f'\n<could-you-prompt-expanded-file "{file_path.absolute()}">\n'
                result += content + "\n"
                result += f'</could-you-prompt-expanded-file "{file_path.absolute()}">\n\n'
            except Exception as e:
                LOGGER.warning(f"COULD_YOU_LOAD_FILE: Error loading {file_path.absolute()}: {e}")

        if not result:
            LOGGER.info(f"COULD_YOU_LOAD_FILE: No files matched pattern '{rel_pattern}'.")

        return result

    return COULD_YOU_LOAD_FILE_PATTERN.sub(_replace, prompt)
