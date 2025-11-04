import json
import os
import sys
from pathlib import Path
from typing import Any

from jsonmerge import merge

from .logging_config import LOGGER
from .mcp_server import MCPServer
from .prompt import enrich_raw_prompt

XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
CONFIG_DIR = Path(XDG_CONFIG_HOME) / "could-you"
GLOBAL_CONFIG_PATH = CONFIG_DIR / "config.json"
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


def load(script_name: str|None = None):
    # Load raw JSON configurations
    g_config_json = _load_raw_json(GLOBAL_CONFIG_PATH)
    local_config_path = _find_up(Path(".").resolve())
    l_config_json = _load_raw_json(local_config_path)
    # Merge configurations with local taking priority
    merged_config_json = merge(g_config_json, l_config_json)

    if script_name:
        # Only load the script config from the user config folder
        local_script_path = local_config_path.parent / f'.could-you-script.{script_name}.json'
        global_script_path = CONFIG_DIR / f'script.{script_name}.json'

        for script_config_path in [local_script_path, global_script_path]:
            if script_config_path.exists():
                LOGGER.info(f"Found script: {script_config_path}")
                break

            LOGGER.info(f"Script does not exist: {script_config_path}")
        else:
            LOGGER.error(f"Script {script_name} does not exist.")
            sys.exit(1)

        s_config_json = _load_raw_json(script_config_path)
        # remove tools merged

        if "mcpServers" in merged_config_json:
            del merged_config_json["mcpServers"]

        merged_config_json = merge(merged_config_json, s_config_json)

    # Parse the merged configuration
    config = _parse_from_json(merged_config_json, local_config_path.parent)

    # Apply defaults
    if not config.prompt:
        config.prompt = DEFAULT_PROMPT

    config.prompt = enrich_raw_prompt(config.prompt)

    if not config.editor:
        config.editor = os.environ.get("EDITOR", "vim")

    # Validate required fields
    if not config.llm:
        LOGGER.error('Must specify "llm" in config')
        sys.exit(1)

    if config.llm["provider"] not in ["boto3", "ollama", "openai"]:
        LOGGER.error(f"supported providers are boto3, ollama, and openai, got {config.llm['provider']}")
        sys.exit(1)

    # Apply environment variables
    for key, value in config.env.items():
        if value is not None:
            os.environ[key] = value

    return config


def init() -> Config:
    g_config_json = _load_raw_json(GLOBAL_CONFIG_PATH)

    with open(CONFIG_FILE_NAME, "w") as l_config:
        # Create a copy to avoid modifying the original
        jsonable = g_config_json.copy()

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
        json.dump(jsonable, l_config, indent=2)

    return load()


def _find_up(current_path: Path) -> Path:
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
    potential_file = current_path / CONFIG_FILE_NAME
    if potential_file.is_file():
        return potential_file

    # Move up to the parent directory
    parent_path = current_path.parent

    # Stop recursion if we've reached the root directory
    if current_path == parent_path:
        LOGGER.error("did not find .could-you-config.json in this or above directories.")
        LOGGER.error("could-you must be run from within a workspace.")
        sys.exit(1)

    # Recurse into the parent directory
    return _find_up(parent_path)


def _load_raw_json(config_file: Path) -> dict[str, Any]:
    """
    Load raw JSON configuration from file.

    Args:
        config_file (Path): Path to the configuration JSON file.

    Returns:
        Dict[str, Any]: Raw JSON configuration or empty dict if file doesn't exist.
    """
    if not config_file.is_file():
        return {}

    try:
        with open(config_file) as file:
            return json.load(file)
    except json.JSONDecodeError as e:
        LOGGER.error(f"Failed to parse the JSON configuration file at {config_file}: {e}")
        sys.exit(1)
    except Exception as e:
        LOGGER.error(f"internal error: Could not load configuration file at {config_file}: {e}")
        sys.exit(1)


def _parse_from_json(json_config: dict[str, Any], root: Path) -> Config:
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
    query = json_config.get("query", None)

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
