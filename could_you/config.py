import importlib.resources
import json
import os
import shutil
from pathlib import Path
from typing import Any

import yaml
from attrs import define, field
from cattrs import ClassValidationError, Converter

import could_you.resources

from .cy_error import CYError, FaultOwner
from .logging_config import LOGGER
from .prompt import enrich_raw_prompt

CONFIG_FILE_NAME = ".could-you-config.json"
DEFAULT_PROMPT = """
Your name is Cy.

You are an agent responsible for helping a software developer perform tasks.

DO ASSUME file content is correct.

DO NOT ASSUME any file edits you have previously made will be persisted, or were correct.

DO NOT ASSUME that you should make file edits, only make file changes if asked. For example, if asked to \"show\" or
\"tell\" only provide an answer.

COULD_YOU_LOAD_FILE(*.md)
"""


@define
class LLMProps:
    provider: str
    init: dict[str, Any] = field(factory=dict)
    args: dict[str, Any] = field(factory=dict)


@define
class MCPServerProps:
    command: str
    args: list[str] = field(factory=list)
    disabled_tools: list[str] = field(factory=list, alias="disabledTools")
    env: dict[str, str] = field(factory=dict)
    enabled: bool = field(factory=lambda: True)


@define
class Config:
    llm: LLMProps
    system_prompt: str | None = field(factory=lambda: DEFAULT_PROMPT, alias="systemPrompt")
    mcp_servers: dict[str, MCPServerProps] = field(factory=dict, alias="mcpServers")
    env: dict[str, str] = field(factory=dict)
    # default query for a script.
    query: str | None = field(factory=lambda: None)


class InvalidConfigError(CYError):
    def __init__(self, message):
        super().__init__(message=message, retriable=False, fault_owner=FaultOwner.USER)


def init() -> Path:
    w_config_dir = Path.cwd() / ".could-you"

    if w_config_dir.exists():
        msg = f"Workspace path already exists, will not overwrite: {w_config_dir}"
        LOGGER.error(msg)
        raise InvalidConfigError(msg)

    user_config_dir = _get_user_config_dir_path()

    if user_config_dir.exists() and user_config_dir.is_dir:
        shutil.copytree(user_config_dir, w_config_dir)

    _copy_global_config(w_config_dir)

    return w_config_dir


def load(script_name: str | None = None) -> tuple[Config, Path]:
    w_config_dir = _find_workspace_config_dir(Path.cwd())
    config_dict = _load_dict(w_config_dir)

    if script_name:
        s_config_dict = _load_dict(w_config_dir, script_name)

        for key, val in s_config_dict.items():
            config_dict[key] = val

    config = _parse_from_dict(config_dict)
    _validate_config(config, w_config_dir)

    return config, w_config_dir


def _load_dict(w_config_dir: Path, script_name: str | None = None) -> dict[str, Any]:
    base_name = "config.json" if not script_name else f"script.{script_name}.json"
    full_name = w_config_dir / base_name
    config_path = _get_preferred_path(full_name)

    if not config_path:
        msg = f'Failed to find configuration file in "{w_config_dir}" (like "{base_name}")'
        LOGGER.error(msg)
        raise InvalidConfigError(msg)

    # config_dict = _load_raw_path(config_path)
    return _load_raw_path(config_path)


def _validate_config(config: Config, w_config_dir: Path):
    # Apply defaults
    if not config.system_prompt:
        config.system_prompt = DEFAULT_PROMPT

    config.system_prompt = enrich_raw_prompt(config.system_prompt)

    # Validate required fields
    if not config.llm or not config.llm.provider:
        msg = 'Must specify "llm" in config'
        LOGGER.error(msg)
        raise InvalidConfigError(msg)

    if config.llm.provider not in ["boto3", "ollama", "openai"]:
        msg = f"Invalid provider. Supported providers are boto3, ollama, and openai, got {config.llm.provider}"
        LOGGER.error(msg)
        raise InvalidConfigError(msg)

    for mcp_props in config.mcp_servers.values():
        mcp_props.args = [arg.replace("$COULD_YOU_WORKSPACE", str(w_config_dir.parent)) for arg in mcp_props.args]

    # Apply environment variables
    for key, value in (config.env or {}).items():
        if value is not None:
            os.environ[key] = value


def _get_user_config_dir_path():
    xdg_config_home = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(xdg_config_home) / "could-you"


def _find_workspace_config_dir(current_path: Path) -> Path:
    """
    Recursively searches upward for the closest file named CONFIG_FILE_NAME.

    Args:
        current_path (Path): The starting directory for the search.
    """
    # Check the current directory first
    config_path = current_path / ".could-you"

    if config_path.exists() and config_path.is_dir:
        return config_path

    # Move up to the parent directory
    parent_path = current_path.parent

    # Stop recursion if we've reached the root directory
    if current_path == parent_path:
        LOGGER.warning("did not find .could-you/ in this or above directories.")
        msg = "could-you must be run from within a workspace."
        LOGGER.error(msg)
        raise InvalidConfigError(msg)

    # Recurse into the parent directory
    return _find_workspace_config_dir(parent_path)


def _get_preferred_path(config_file: Path) -> Path | None:
    for ext in (".json", ".yaml", ".yml"):
        config_with_ext = config_file.with_suffix(ext)

        if config_with_ext.is_file():
            return config_with_ext

    return None


def _copy_global_config(w_config_dir: Path):
    """
    Try all possible script config locations (workspace, user, package resource).
    Returns (kind, path_or_name_or_resourcehandle) or (None, None) if not found.
    kind: 'file' or 'resource'
    """
    for resource in importlib.resources.files(could_you.resources).iterdir():
        if not resource.is_file():
            continue

        if resource.suffix not in (".json", ".yaml", ".yml"):
            continue

        dest = w_config_dir / os.path.basename(str(resource))

        if dest.exists():
            LOGGER.warning(f"File exists in destination ({dest}), will not overwrite with global version ({resource})")
            continue

        with resource.open("r") as f:
            LOGGER.info(f"Writing file {dest} from global {resource}")
            dest.write_text(f.read())


def _load_raw_path(config_path: Path) -> dict[str, Any]:
    """
    Load raw JSON configuration from file.

    Args:
        config_file (Path): Path to the configuration JSON file.

    Returns:
        Dict[str, Any]: Raw JSON configuration or empty dict if file doesn't exist.
    """
    if not isinstance(config_path, Path):
        return {}

    if not config_path.is_file():
        return {}

    try:
        with open(config_path) as file:
            if config_path.suffix == ".json":
                return json.load(file)

            return yaml.safe_load(file)
    except Exception as e:
        msg = f"Failed to load configuration file at {config_path}: {e}"
        LOGGER.error(msg)
        raise InvalidConfigError(msg) from e


def _parse_from_dict(json_config: dict[str, Any]) -> Config:
    """
    Parse a Config object from merged JSON configuration.

    Args:
        json_config (Dict[str, Any]): Merged JSON configuration.

    Returns:
        Config: Parsed configuration object.
    """
    try:
        converter = Converter(use_alias=True)
        config = converter.structure(json_config, Config)
    except ClassValidationError as cve:
        raise InvalidConfigError("Must specify all required fields values") from cve

    return config
