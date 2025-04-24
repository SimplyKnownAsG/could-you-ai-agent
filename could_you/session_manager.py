import os
import json
from pathlib import Path


class SessionManager:
    def __init__(self, cache_path):
        self.cache_path = cache_path
        self.current_session = None

    def list_sessions(self):
        """List all existing sessions."""
        sessions = []
        for session_file in self.cache_path.glob("*.json"):
            with open(session_file, "r") as f:
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
            with open(self.current_session, "r") as f:
                return json.load(f)
        return None
