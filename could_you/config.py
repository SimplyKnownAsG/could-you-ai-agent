import importlib.resources
import json
import os
from pathlib import Path
from typing import Any

import yaml
from jsonmerge import merge

import could_you.resources

from .cy_error import CYError, FaultOwner
from .dynamic import Dynamic
from .logging_config import LOGGER
from .mcp_server import MCPServer
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


class LLMProps(Dynamic):
    provider: str
    init: dict[str, Any]
    args: dict[str, Any]


class Config(Dynamic):
    system_prompt: str | None = None
    llm: LLMProps
    servers: list[MCPServer]
    root: Path
    editor: str | None = os.environ.get("EDITOR", "vim")
    env: dict[str, str]
    # default query for a script.
    query: str | None

class InvalidConfigError(CYError):
    def __init__(self, message):
        super().__init__(message=message, retriable=False, fault_owner=FaultOwner.USER)


def init() -> Config:
    u_config_dict = _load_raw_path(_get_user_config_path())

    with open(CONFIG_FILE_NAME, "w") as w_config:
        # Create a copy to avoid modifying the original
        jsonable = u_config_dict.copy()

        # Remove root if it exists (shouldn't be in local config)
        if "root" in jsonable:
            del jsonable["root"]

        # Remove None values
        for key in list(jsonable.keys()):
            if jsonable[key] is None:
                del jsonable[key]

        # Handle servers -> mcpServers conversion
        servers = jsonable.get("servers", [])
        if "servers" in jsonable:
            del jsonable["servers"]

        mcp_servers = jsonable.get("mcpServers", {})

        # Convert old server format to new mcpServers format if needed
        for s in servers:
            name = s["name"]
            server_config = s.copy()
            del server_config["name"]
            mcp_servers[name] = server_config

        mcp_servers["filesystem"] = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", os.path.abspath(".")],
        }
        jsonable["mcpServers"] = mcp_servers
        json.dump(jsonable, w_config, indent=2)

    return load()


def load(script_name: str | None = None):
    # this uses prefixes
    #   u - user
    #   w - workspace
    #   s - script
    #   m - merged
    # Load raw JSON configurations
    cwd = Path.cwd()
    u_config_path = _get_user_config_path()
    u_config_dict = _load_raw_path(u_config_path)
    w_config_path = _get_workspace_config_path(cwd, required=script_name is None)
    w_config_dict = _load_raw_path(w_config_path)
    # Merge configurations with local taking priority
    m_config_dict = merge(u_config_dict, w_config_dict)

    w_dir = w_config_path.parent if w_config_path else cwd

    if script_name:
        # Load script from the current folder, or from the XDG config
        w_script_path = w_dir / f".could-you-script.{script_name}.json"
        g_script_path = _get_user_config_dir_path() / f"script.{script_name}.json"

        for s_config_base_path in [w_script_path, g_script_path]:
            s_config_path = _get_preferred_path(s_config_base_path)

            if s_config_path:
                LOGGER.info(f"Found script: {s_config_path}")
                s_config_dict = _load_raw_path(s_config_path)
                break

            LOGGER.info(f"Script does not exist: {s_config_base_path}")
        else:
            s_config_dict = _load_global_script(script_name)

        # remove tools merged
        if "mcpServers" in m_config_dict:
            del m_config_dict["mcpServers"]

        m_config_dict = merge(m_config_dict, s_config_dict)

    # Parse the merged configuration
    config = _parse_from_dict(m_config_dict, w_dir)

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

    # Apply environment variables
    for key, value in (config.env or {}).items():
        if value is not None:
            os.environ[key] = value

    return config


def _get_user_config_path():
    return _get_preferred_path(_get_user_config_dir_path() / "config.json")


def _get_user_config_dir_path():
    xdg_config_home = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(xdg_config_home) / "could-you"


def _get_workspace_config_path(current_path: Path, *, required: bool) -> Path | None:
    """
    Recursively searches upward for the closest file named CONFIG_FILE_NAME.

    Args:
        current_path (Path): The starting directory for the search.
                           Defaults to the current directory (".")

    Returns:
        Path | None: A Path object pointing to the closest matching file,
                     or None if the file is not found.
    """
    # Check the current directory first
    config_path = _get_preferred_path(current_path / CONFIG_FILE_NAME)

    if config_path:
        return config_path

    # Move up to the parent directory
    parent_path = current_path.parent

    # Stop recursion if we've reached the root directory
    if current_path == parent_path:
        LOGGER.warning("did not find .could-you-config.json in this or above directories.")

        if required:
            msg = "could-you must be run from within a workspace."
            LOGGER.error(msg)
            raise InvalidConfigError(msg)

        return None

    # Recurse into the parent directory
    return _get_workspace_config_path(parent_path, required=required)


def _get_preferred_path(config_file: Path) -> Path | None:
    for ext in (".json", ".yaml", ".yml"):
        config_with_ext = config_file.with_suffix(ext)

        if config_with_ext.is_file():
            return config_with_ext

    return None


def _load_global_script(script_name: str):
    """
    Try all possible script config locations (workspace, user, package resource).
    Returns (kind, path_or_name_or_resourcehandle) or (None, None) if not found.
    kind: 'file' or 'resource'
    """

    for ext in (".json", ".yaml", ".yml"):
        resource_name = f"script.{script_name}{ext}"
        if importlib.resources.is_resource(could_you.resources, resource_name):
            with importlib.resources.open_text(could_you.resources, resource_name) as f:
                return yaml.safe_load(f)

    msg = f"Script {script_name} does not exist (checked: workspace, user, global resources)."
    LOGGER.error(msg)
    raise InvalidConfigError(msg)


def _load_raw_path(config_path: Path | None) -> dict[str, Any]:
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


def _parse_from_dict(json_config: dict[str, Any], root: Path) -> Config:
    """
    Parse a Config object from merged JSON configuration.

    Args:
        json_config (Dict[str, Any]): Merged JSON configuration.
        root (Path): Root directory for the configuration.

    Returns:
        Config: Parsed configuration object.
    """
    config = Config(**json_config, root=root)
    config.llm = LLMProps(config.llm)
    servers = []

    # Parse MCP servers
    mcp_servers = json_config.get("mcpServers", {})
    for name, server_config in mcp_servers.items():
        missing = [key for key in ["command", "args"] if key not in server_config]

        if any(missing):
            raise ValueError(f"The MCP Server '{name}' file is missing required keys: {', '.join(missing)}.")

        server = MCPServer(name=name, **server_config)
        servers.append(server)

    config.servers = servers
    return config
