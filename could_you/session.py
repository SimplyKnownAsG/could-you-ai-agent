import json
import os
from collections.abc import Callable
from pathlib import Path

from .config import Config, init, load, sync_workspace
from .dialogue import Dialogue
from .logging_config import LOGGER
from .tools.subagent_tools import SubagentServer

# Constants for XDG paths
XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
XDG_CACHE_HOME = os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")
CACHE_PATH = Path(XDG_CACHE_HOME) / "could-you"

# Ensure directories exist
CACHE_PATH.mkdir(parents=True, exist_ok=True)


class Session:
    w_config_dir: Path
    config: Config
    script_name: str | None
    dialogue: Dialogue

    def __init__(self, w_config_dir: Path, script_name: str | None, config: Config, depth: int = 0):
        self.w_config_dir = w_config_dir
        self.script_name = script_name
        self.config = config
        self.dialogue = Dialogue(self.w_config_dir, props=self.config.dialogue)
        self.depth = depth
        self.subagent_server = SubagentServer(subagent_props=config.tools.subagent, depth=depth)

    @property
    def workspace_dir(self) -> Path:
        return self.w_config_dir.parent

    @property
    def tmp_dir(self) -> Path:
        return self.w_config_dir / "tmp"

    async def __aenter__(self):
        self.dialogue.__enter__()
        self.tmp_dir.mkdir(exist_ok=True)
        await self.subagent_server.__aenter__()
        return self

    async def __aexit__(self, ex_type, ex_val, ex_tb):
        try:
            await self.subagent_server.__aexit__(ex_type, ex_val, ex_tb)
        finally:
            self.dialogue.__exit__(ex_type, ex_val, ex_tb)


class SessionManager:
    sessions_file: Path
    sessions: dict[str, dict]

    def __init__(self, *, cache_path: Path = CACHE_PATH):
        self.sessions_file = cache_path / "sessions.json"
        self.sessions = {}

    async def __aenter__(self):
        if os.path.exists(self.sessions_file):
            with open(self.sessions_file) as f:  # noqa: ASYNC230 - small local metadata file
                self.sessions = json.load(f)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        with open(self.sessions_file, "w") as f:  # noqa: ASYNC230 - small local metadata file
            json.dump(self.sessions, f, indent=2)

    def init_session(self):
        w_config_dir = init()
        self.sessions[str(w_config_dir)] = {}
        LOGGER.info(f"initialized config dir: {w_config_dir}")
        return w_config_dir

    def sync_workspace(self):
        w_config_dir = sync_workspace()
        self.sessions[str(w_config_dir)] = {}
        LOGGER.info(f"synced config dir: {w_config_dir}")
        return w_config_dir

    def load_session(self, script_name: str | None, override: Callable[[Config], None], *, depth: int = 0):
        config, w_config_dir = load(script_name)
        override(config)
        session = Session(w_config_dir, script_name, config, depth=depth)
        self.sessions[str(w_config_dir.parent)] = {}
        return session

    def list(self):
        for root in self.sessions:
            LOGGER.info(f"Session root: {root}")
