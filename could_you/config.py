import json
import os
import sys
from pathlib import Path
import subprocess
from typing import List, Dict, Any, Set

from .mcp_server import MCPServer
from .message import _Dynamic


XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
GLOBAL_CONFIG_PATH = Path(XDG_CONFIG_HOME) / "could-you" / "config.json"
CONFIG_FILE_NAME = ".could-you-config.json"


class Config:
    prompt: str | None
    llm: Dict[str, Any]
    servers: List[MCPServer]
    root: Path
    editor: str | None
    env: Dict[str, str]

    def __init__(
        self,
        *,
        prompt: str | None,
        llm: Dict[str, Any],
        servers: List[MCPServer],
        root: Path,
        editor: str | None = None,
        env: Dict[str, str],
    ):
        self.prompt = prompt
        self.llm = llm
        self.servers = servers
        self.root = root
        self.editor = editor
        self.env = env or {}


def load():
    g_config = _parse(GLOBAL_CONFIG_PATH)
    local_config_path = _find_up(Path(".").resolve())
    l_config = _parse(local_config_path)

    # Merge configurations with local taking priority
    llm = l_config.llm or g_config.llm
    prompt = l_config.prompt or g_config.prompt or "You are an agent to help a software developer"
    editor = l_config.editor or g_config.editor or os.environ.get("EDITOR", "vim")

    # Merge env dictionaries with local taking priority
    env = g_config.env.copy()
    env.update(l_config.env)  # Local overrides global

    if not llm:
        print(f'ERROR: Must specify "llm" in config')
        sys.exit(1)

    if llm["provider"] not in ["boto3", "ollama"]:
        print(f"ERROR: supported providers are boto3 and ollama, got {llm['provider']}")
        sys.exit(1)

    servers = l_config.servers

    for g_server in g_config.servers:
        if not any(g_server.name == s.name for s in servers):
            print(f"Adding {g_server.name} MCP server from global config")
            servers.append(g_server)
        else:
            print(f"Ignoring {g_server.name} MCP server from global config")

    # Create the final config
    config = Config(
        prompt=prompt, llm=llm, servers=servers, root=l_config.root, editor=editor, env=env
    )

    # Apply environment variables
    for key, value in config.env.items():
        if value is not None:
            os.environ[key] = value

    return config


def init() -> Path:
    g_config = _parse(GLOBAL_CONFIG_PATH)

    with open(CONFIG_FILE_NAME, "w") as l_config:
        jsonable = _Dynamic(g_config).to_dict()
        del jsonable["root"]

        for key in list(jsonable.keys()):
            if jsonable[key] is None:
                del jsonable[key]

        servers = jsonable.get("servers", [])
        del jsonable["servers"]

        mcp_servers = jsonable["mcpServers"] = {}

        for s in servers:
            name = s["name"]
            del s["name"]
            mcp_servers[name] = s

        dirnames = list_directories(".")

        mcp_servers["filesystem"] = {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                *dirnames,
            ],
        }

        json.dump(jsonable, l_config, indent=2)

    return Path(CONFIG_FILE_NAME)


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
        print("error: did not find .could-you-config.json in this or above directories.")
        print("error: could-you must be run from within a workspace.")
        sys.exit(1)

    # Recurse into the parent directory
    return _find_up(parent_path)


def _parse(config_file: Path) -> Config:
    """
    Load the configuration JSON file compliant with the Claude Desktop format.

    Args:
        config_file (str): Path to the configuration JSON file.

    Raises:
        ValueError: If the JSON file is missing required keys or is malformed.
    """
    llm = {}
    servers = []

    config = Config(prompt=None, llm=llm, servers=servers, root=config_file.parent, env={})

    if not config_file.is_file():
        return config

    try:
        with open(config_file, "r") as file:
            json_config = json.load(file)

        config.prompt = json_config.get("systemPrompt", None)
        llm.update(json_config.get("llm", {}))
        config.env.update(json_config.get("env", {}))

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


def list_directories(root_path: str) -> List[str]:
    """
    Recursively lists all unique directories, using `git ls-files` for folders containing `.git`.
    Includes parent directories, ignoring hidden directories and symlinks.

    Args:
        root_path (str): The root directory to start traversal.

    Returns:
        List[str]: A list of unique directory paths.
    """
    root_path = os.path.abspath(root_path)
    result = set([root_path])

    for dirpath, dirnames, _ in os.walk(root_path):
        # If the directory contains a `.git` folder, use `git ls-files` and short circuit
        if ".git" in dirnames:
            result.update(run_git_ls_files(dirpath))
            dirnames[:] = []  # Stop os.walk from descending into subdirectories
            continue

        # Remove hidden directories and symlinks
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".") and not os.path.islink(os.path.join(dirpath, d))
        ]

        # Add the current directory to the result set
        result.add(dirpath)

    return sorted(result)


def run_git_ls_files(repo_path: str) -> Set[str]:
    """
    Runs `git ls-files` in the given repository path and returns the unique directories,
    including parent directories of all files.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        files = result.stdout.splitlines()
        directories = set()

        for file in files:
            # Add all parent directories of the file
            dir_path = os.path.dirname(file)

            while dir_path:
                directories.add(dir_path)
                dir_path = os.path.dirname(dir_path)

        return {os.path.join(repo_path, d) for d in directories}
    except subprocess.CalledProcessError:
        # If `git ls-files` fails, return an empty set
        return set()
