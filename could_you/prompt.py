"""
Utilities for processing and expanding prompt text, including COULD_YOU_LOAD_FILE directives safely.
"""

import getpass
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from attrs import define, field

from .logging_config import LOGGER
from .metadata import LoadedFileMetadata, PromptMetadata

# Pattern to match COULD_YOU_LOAD_FILE(relative/path.md or glob)
COULD_YOU_LOAD_FILE_PATTERN = re.compile(r"^COULD_YOU_LOAD_FILE\((.+)\)$", re.MULTILINE)
COULD_YOU_DEFAULT_PROMPT_PATTERN = re.compile(r"^COULD_YOU_DEFAULT_PROMPT(\(\))?$", re.MULTILINE)
COULD_YOU_AGENT_NAME_PATTERN = re.compile(r"^COULD_YOU_AGENT_NAME$", re.MULTILINE)
# Pattern to match COULD_YOU_EXPAND_ENV(NAME) on its own line.
# NAME must match the usual env-var shape: start with letter or underscore,
# followed by letters, digits, or underscores. Line-anchored like the other
# directives so the expansion is explicit at the source level.
COULD_YOU_EXPAND_ENV_PATTERN = re.compile(r"^COULD_YOU_EXPAND_ENV\(([A-Za-z_][A-Za-z0-9_]*)\)$", re.MULTILINE)

DEFAULT_PROMPT_TEMPLATE = """
COULD_YOU_AGENT_NAME

> NOTE
>
> The following files are loaded fresh each turn from the workspace's
> `.could-you/` directory and wrapped in `<could-you-prompt-expanded-file>`
> tags. Each file serves a specific purpose:
>
> - `FORMATIVE.md` — stable, high-confidence memories that shape how I interact with this user specifically; changes slowly
> - `SYSTEM_PROMPT.md` — standing identity, behaviour, and operating rules
> - `MEMORY.md` — durable but fluid continuity: project state, decisions, implementation facts, and continuation points
> - `TODO.md` — active open loops, next actions, and current highest priority
>
> If a file was modified during this turn, the expanded content below
> reflects the state before that modification.

COULD_YOU_LOAD_FILE(.could-you/FORMATIVE.md)

COULD_YOU_LOAD_FILE(.could-you/SYSTEM_PROMPT.md)

COULD_YOU_LOAD_FILE(.could-you/MEMORY.md)

COULD_YOU_LOAD_FILE(.could-you/TODO.md)

> WARNING
>
> This is the default template which auto-loads markdown files in the
> could-you workspace root. The user may not have configured this
> intentionally. The following markdown files are also wrapped in
> `<could-you-prompt-expanded-file>` tags but may not have been
> intentionally included in the system prompt. After you have intentional
> `.could-you` memory files (above this WARNING), consider asking the user
> to remove `COULD_YOU_LOAD_FILE(*.md)` from `.could-you/config.yaml` if
> they appear to be unmaintained.

COULD_YOU_LOAD_FILE(*.md)
"""


@define(frozen=True)
class PromptExpansionResult:
    text: str
    metadata: PromptMetadata = field(factory=PromptMetadata)


def enrich_raw_prompt(prompt: str, workspace_root: Path | None = None) -> PromptExpansionResult:
    """
    Public entrypoint: applies all prompt enrichments to the raw prompt string.
    Add additional prompt-enriching logic here as needed.

    Args:
        prompt: The raw prompt string to enrich.
        workspace_root: The workspace root directory to use as the base for
            COULD_YOU_LOAD_FILE glob patterns. Defaults to the current working
            directory when not provided. Always pass this explicitly when the
            workspace root is known so that globs work correctly even when
            could-you is invoked from a sub-directory of the workspace.
    """
    prompt = _expand_cy_default_pattern(prompt)
    prompt = _expand_cy_agent_name_pattern(prompt)
    prompt = _expand_cy_expand_env_pattern(prompt)
    return _expand_cy_load_file(prompt, workspace_root=workspace_root)


def _expand_cy_default_pattern(prompt: str) -> str:
    return COULD_YOU_DEFAULT_PROMPT_PATTERN.sub(_default_prompt(), prompt)


def _default_prompt() -> str:
    return DEFAULT_PROMPT_TEMPLATE


def _expand_cy_agent_name_pattern(prompt: str) -> str:
    return COULD_YOU_AGENT_NAME_PATTERN.sub(_agent_name_sentence(), prompt)


def _agent_name_sentence() -> str:
    return f"Your name is {_default_agent_name()}."


def _expand_cy_expand_env_pattern(prompt: str) -> str:
    """Replace each ``COULD_YOU_EXPAND_ENV(NAME)`` line with the value of ``$NAME``.

    When the referenced variable is not set (or is set to an empty string),
    substitute a visible marker (``<COULD_YOU_EXPAND_ENV: NAME not set>``)
    and log a warning. We deliberately do not raise: the prompt pipeline runs
    on every query, and an unset variable is often a legitimate state (e.g.
    ``COULD_YOU_INCIDENT_DIR`` is only set inside the recovery subprocess).
    The marker makes the missing expansion visible both in logs and to the
    model reading the prompt.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = os.environ.get(name)
        if value is None or value == "":
            LOGGER.warning(f"COULD_YOU_EXPAND_ENV: environment variable {name!r} is not set")
            return f"<COULD_YOU_EXPAND_ENV: {name} not set>"
        return value

    return COULD_YOU_EXPAND_ENV_PATTERN.sub(_replace, prompt)


def _default_agent_name() -> str:
    try:
        user = getpass.getuser()
    except OSError:
        user = "usr"

    user = user.strip() or "usr"
    return f"{user}-borg"


def _date_sentence(now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now().astimezone()
    tz_name = now.strftime("%Z")
    datetime_str = now.strftime("%Y-%m-%dT%H:%M")
    monday = now.date() - timedelta(days=now.weekday())
    week_of = f"{monday.strftime('%A, %B')} {monday.day}"
    return f"The current time is {datetime_str} {tz_name}, the week of {week_of}."


def _expand_cy_load_file(prompt: str, workspace_root: Path | None = None) -> PromptExpansionResult:
    """
    Replace all COULD_YOU_LOAD_FILE(pattern) in the prompt with the actual contents of all files matching the glob pattern.
    """
    root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
    cwd = str(root)
    loaded_files: list[LoadedFileMetadata] = []

    def _replace(match):
        rel_pattern = match.group(1).strip()
        expanded_paths = [Path(p) for p in sorted(root.glob(rel_pattern))]
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
