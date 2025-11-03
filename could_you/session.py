import json
import os
from pathlib import Path

from .config import init, load
from .logging_config import LOGGER

# Constants for XDG paths
XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
XDG_CACHE_HOME = os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")
CACHE_PATH = Path(XDG_CACHE_HOME) / "could-you"

# Ensure directories exist
CACHE_PATH.mkdir(parents=True, exist_ok=True)

# # TODO: use Session
# class Session:
#     config: Config
#     message_history: MessageHistory


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
        config = init()
        self.sessions[str(config.root)] = {}
        LOGGER.info(f"initialized config file: {config.root}")
        return config

    def load_session(self):
        config = load()
        self.sessions[str(config.root)] = {}
        return config

    def list(self):
        for root in self.sessions:
            LOGGER.info(f"Session root: {root}")
