import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonmerge import merge

from .logging_config import LOGGER
from .mcp_server import MCPServer
from .prompt import enrich_raw_prompt
from .cy_error import CYError, FaultOwner

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


class Config:
    prompt: str | None
    llm: dict[str, Any]
    servers: list[MCPServer]
    root: Path
    editor: str | None
    env: dict[str, str]
    # default query for a script.
    query: str | None

    def __init__(
        self,
        *,
        prompt: str | None,
        llm: dict[str, Any],
        servers: list[MCPServer],
        root: Path,
        editor: str | None = None,
        env: dict[str, str],
        query: str | None = None,
    ):
        self.prompt = prompt
        self.llm = llm
        self.servers = servers
        self.root = root
        self.editor = editor
        self.env = env or {}
        self.query = query


class InvalidConfigError(CYError):

    def __init__(self, message):
        super().__init__(message=message, retriable=False, fault_owner=FaultOwner.USER)


def init() -> Config:
    g_config_dict = _load_raw_path(_get_global_config_path())

    with open(CONFIG_FILE_NAME, "w") as w_config:
        # Create a copy to avoid modifying the original
        jsonable = g_config_dict.copy()

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
    #   g - global
    #   w - workspace
    #   s - script
    #   m - merged
    # Load raw JSON configurations
    g_config_path = _get_global_config_path()
    g_config_dict = _load_raw_path(g_config_path)
    w_config_path = _get_workspace_config_path(Path(".").resolve())
    w_config_dict = _load_raw_path(w_config_path)
    # Merge configurations with local taking priority
    m_config_dict = merge(g_config_dict, w_config_dict)

    if script_name:
        # Only load the script config from the user config folder
        w_script_path = w_config_path.parent / f".could-you-script.{script_name}.json"
        g_script_path = _get_global_config_dir_path() / f"script.{script_name}.json"

        for s_config_base_path in [w_script_path, g_script_path]:
            s_config_path = _get_preferred_path(s_config_base_path)

            if s_config_path:
                LOGGER.info(f"Found script: {s_config_path}")
                break

            LOGGER.info(f"Script does not exist: {s_config_base_path}")
        else:
            LOGGER.error(f"Script {script_name} does not exist.")
            sys.exit(1)

        s_config_dict = _load_raw_path(s_config_path)
        # remove tools merged

        if "mcpServers" in m_config_dict:
            del m_config_dict["mcpServers"]

        m_config_dict = merge(m_config_dict, s_config_dict)

    # Parse the merged configuration
    config = _parse_from_dict(m_config_dict, w_config_path.parent)

    # Apply defaults
    if not config.prompt:
        config.prompt = DEFAULT_PROMPT

    config.prompt = enrich_raw_prompt(config.prompt)

    if not config.editor:
        config.editor = os.environ.get("EDITOR", "vim")

    # Validate required fields
    if not config.llm:
        msg = 'Must specify "llm" in config'
        LOGGER.error(msg)
        raise InvalidConfigError(msg)

    if config.llm["provider"] not in ["boto3", "ollama", "openai"]:
        msg = f"supported providers are boto3, ollama, and openai, got {config.llm['provider']}"
        LOGGER.error(msg)
        raise InvalidConfigError(msg)

    # Apply environment variables
    for key, value in config.env.items():
        if value is not None:
            os.environ[key] = value

    return config


def _get_global_config_path():
    return _get_preferred_path(_get_global_config_dir_path() / "config.json")


def _get_global_config_dir_path():
    xdg_config_home = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(xdg_config_home) / "could-you"


def _get_workspace_config_path(current_path: Path) -> Path:
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
        LOGGER.error("did not find .could-you-config.json in this or above directories.")
        msg = "could-you must be run from within a workspace."
        LOGGER.error(msg)
        raise InvalidConfigError(msg)

    # Recurse into the parent directory
    return _get_workspace_config_path(parent_path)


def _get_preferred_path(config_file: Path):
    for ext in ('.json', '.yaml', '.yml'):
        config_with_ext = config_file.with_suffix(ext)

        if config_with_ext.is_file():
            return config_with_ext


def _load_raw_path(config_path: Path|None) -> dict[str, Any]:
    """
    Load raw JSON configuration from file.

    Args:
        config_file (Path): Path to the configuration JSON file.

    Returns:
        Dict[str, Any]: Raw JSON configuration or empty dict if file doesn't exist.
    """
    if config_path is None or not config_path.is_file():
        return {}

    try:
        with open(config_path) as file:
            if config_path.suffix == '.json':
                return json.load(file)
            else:
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
    llm = json_config.get("llm", {})
    servers = []
    env = json_config.get("env", {})
    prompt = json_config.get("systemPrompt")
    editor = json_config.get("editor")
    query = json_config.get("query")

    # Parse MCP servers
    mcp_servers = json_config.get("mcpServers", {})
    for name, server_config in mcp_servers.items():
        missing = [key for key in ["command", "args"] if key not in server_config]

        if any(missing):
            raise ValueError(f"The MCP Server '{name}' file is missing required keys: {', '.join(missing)}.")

        # Extract disabled_tools if present
        disabled_tools = server_config.get("disabledTools", [])

        # Create server config without disabled_tools for MCPServer constructor
        server_kwargs = server_config.copy()
        server_kwargs.pop("disabledTools", None)

        server = MCPServer(name=name, disabled_tools=disabled_tools, **server_kwargs)
        servers.append(server)

    return Config(prompt=prompt, llm=llm, servers=servers, root=root, editor=editor, env=env, query=query)
