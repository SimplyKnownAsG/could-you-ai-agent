import json
import os
from pathlib import Path

# Constants for XDG paths
XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
XDG_CACHE_HOME = os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")
CONFIG_PATH = Path(XDG_CONFIG_HOME) / "could-you" / "config.json"
CACHE_PATH = Path(XDG_CACHE_HOME) / "could-you"

# Ensure directories exist
CACHE_PATH.mkdir(parents=True, exist_ok=True)
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


class SessionManager:
    def __init__(self, *, cache_path=CACHE_PATH, config_path=CONFIG_PATH):
        self.cache_path = cache_path
        self.current_session = None

    def init_session(self):
        """Create a new session."""

    def list_sessions(self):
        """List all existing sessions."""
        sessions = []
        for session_file in self.cache_path.glob("*.json"):
            with open(session_file) as f:
                session_data = json.load(f)
                sessions.append(
                    {
                        "name": session_file.stem,
                        "tokens_used": session_data.get("tokens_used", 0),
                        "directory": session_data.get("directory", "Unknown"),
                    }
                )
        return sessions

    def get_current_session(self):
        """Get the current session, if any."""
        if self.current_session and self.current_session.exists():
            with open(self.current_session) as f:
                return json.load(f)
        return None
