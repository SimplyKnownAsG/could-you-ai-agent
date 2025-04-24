import argparse
import os
import json
from pathlib import Path
from .session_manager import SessionManager

# Constants for XDG paths
XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
XDG_CACHE_HOME = os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")
CONFIG_PATH = Path(XDG_CONFIG_HOME) / "could-you" / "config.json"
CACHE_PATH = Path(XDG_CACHE_HOME) / "could-you"

# Ensure directories exist
CACHE_PATH.mkdir(parents=True, exist_ok=True)
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Could-You MCP CLI")

    # Define a mutually exclusive group
    group = parser.add_mutually_exclusive_group()

    group.add_argument("query", nargs="?", help="A question or request to process")
    group.add_argument("-l", "--list-sessions", action="store_true", help="List existing sessions")
    group.add_argument(
        "-i", "--init-session", action="store_true", help="Initialize a session in this directory"
    )
    group.add_argument(
        "-c", "--clear-sessions", action="store_true", help="Clear existing sessions"
    )
    group.add_argument(
        "-d", "--delete-session", metavar="session_path", help="Delete a specific session"
    )

    args = parser.parse_args()

    session_manager = SessionManager(CACHE_PATH)

    if args.list_sessions:
        # List all sessions
        sessions = session_manager.list_sessions()
        for session in sessions:
            print(
                f"Session: {session['name']}, Tokens Used: {session['tokens_used']}, Directory: {session['directory']}"
            )
    elif args.init_session:
        # Create or switch to a session
        session_manager.switch_session(args.session)
    elif args.delete_session:
        # Create or switch to a session
        session_manager.delete_session(args.delete_session)
    elif args.clear_sessions:
        # Create or switch to a session
        session_manager.clear_sessions()
    elif args.query:
        # Handle a user query
        session = session_manager.get_current_session()
        if session:
            print(f"Processing query in session: {session['name']}")
            # Here, you would process the query and return a response
            print(f"Query: {args.query}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
