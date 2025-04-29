import json
import sys
import os
from pathlib import Path
from typing import List, NamedTuple, Dict, Any
from .mcp_server import MCPServer

XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
GLOBAL_CONFIG_PATH = Path(XDG_CONFIG_HOME) / "could-you" / "config.json"
CONFIG_FILE_NAME = ".could-you-config.json"


class Config:
    llm: Dict[str, Any]
    servers: List[MCPServer]

    def __init__(self, llm: Dict[str, Any], servers: List[MCPServer]):
        self.llm = llm
        self.servers = servers


def load():
    g_config = _parse(GLOBAL_CONFIG_PATH if GLOBAL_CONFIG_PATH.is_file() else None)
    local_config_path = _find_up(Path(".").resolve())
    l_config = _parse(local_config_path)
    print("GRAHAM", l_config)
    llm = l_config.llm or g_config.llm

    if not llm:
        print(f'Must specify "llm" in config')
        sys.exit(1)

    servers = l_config.servers

    for g_server in g_config.servers:
        if not any(g_server.name == s.name for s in servers):
            print(f"Adding {g_server.name} MCP server from global config")
            servers.append(g_server)
        else:
            print(f"Ignoring {g_server.name} MCP server from global config")

    return Config(llm, servers)


def _find_up(current_path: Path) -> Path | None:
    """
    Recursively searches upward for the closest file named CONFIG_FILE_NAME.

    Args:
        start_path (Path): The starting directory for the search.
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
        return None

    # Recurse into the parent directory
    return _find_up(parent_path)


def _parse(config_file: Path | None) -> Config:
    """
    Load the configuration JSON file compliant with the Claude Desktop format.

    Args:
        config_file (str): Path to the configuration JSON file.

    Raises:
        ValueError: If the JSON file is missing required keys or is malformed.
    """
    llm = {}
    servers = []

    config = Config(llm=llm, servers=servers)

    if config_file is None:
        return config

    try:
        with open(config_file, "r") as file:
            json_config = json.load(file)

        llm.update(json_config.get("llm", {}))

        for name, server_config in json_config["mcpServers"].items():
            if not all(key in server_config for key in ["command", "args"]):
                raise ValueError(
                    "The configuration file is missing required keys: 'name', 'command', or 'args'."
                )

            server = MCPServer(name=name, **server_config)
            servers.append(server)

    except json.JSONDecodeError as e:
        print(f"Failed to parse the JSON configuration file at {config_file}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"internal error: Could not load configuration file at {config_file}: {e}")
        sys.exit(1)

    return config
