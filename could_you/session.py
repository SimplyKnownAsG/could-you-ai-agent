import json
import os
from pathlib import Path

from .config import Config, init, load
from .dialogue import Dialogue
from .logging_config import LOGGER

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

    def __init__(self, w_config_dir: Path, script_name: str | None, config: Config):
        self.w_config_dir = w_config_dir
        self.script_name = script_name
        self.config = config

    def dialogue(self, *, load: bool | None = None, store: bool | None = None):
        return Dialogue(
            self.w_config_dir,
            load=self.config.dialogue.load if load is None else load,
            store=self.config.dialogue.store if store is None else store,
        )


class SessionManager:
    sessions_file: Path
    sessions: dict[str, dict]

    def __init__(self, *, cache_path: Path = CACHE_PATH):
        self.sessions_file = cache_path / "sessions.json"
        self.sessions = {}

    def __enter__(self):
        if os.path.exists(self.sessions_file):
            with open(self.sessions_file) as f:
                self.sessions = json.load(f)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        with open(self.sessions_file, "w") as f:
            json.dump(self.sessions, f, indent=2)

    def init_session(self):
        w_config_dir = init()
        self.sessions[str(w_config_dir)] = {}
        LOGGER.info(f"initialized config dir: {w_config_dir}")
        return w_config_dir

    def load_session(self, script_name: str | None):
        config, w_config_dir = load(script_name)
        session = Session(w_config_dir, script_name, config)
        self.sessions[str(w_config_dir.parent)] = {}
        return session

    def list(self):
        for root in self.sessions:
            LOGGER.info(f"Session root: {root}")
