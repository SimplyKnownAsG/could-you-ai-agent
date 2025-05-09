import asyncio
import argparse
import tempfile
import subprocess
from .session_manager import SessionManager
from .mcp_host import MCPHost
from .config import load, init
from .message_history import MessageHistory


async def amain():
    parser = argparse.ArgumentParser(description="Could-You MCP CLI")

    # Define a mutually exclusive group
    group = parser.add_mutually_exclusive_group()

    group.add_argument("query", nargs="?", help="A question or request to process")
    group.add_argument("-l", "--list-sessions", action="store_true", help="List existing sessions")
    group.add_argument(
        "-i", "--init-session", action="store_true", help="Initialize a session in this directory"
    )
    group.add_argument(
        "-d", "--delete-session", metavar="session_path", help="Delete a specific session"
    )

    args = parser.parse_args()

    session_manager = SessionManager()

    if args.list_sessions:
        # List all sessions
        sessions = session_manager.list_sessions()
        for session in sessions:
            print(
                f"Session: {session['name']}, Tokens Used: {session['tokens_used']}, Directory: {session['directory']}"
            )
    elif args.init_session:
        # Create or switch to a session
        l_config_path = init()
        print(f"initialized config file: {l_config_path}")
    elif args.delete_session:
        # Create or switch to a session
        session_manager.delete_session(args.delete_session)
    else:
        config = load()
        query = args.query if args.query else _get_editor_input(config)

        if not query:
            parser.print_help()
            return

        with MessageHistory(config.root) as message_history:
            async with MCPHost(config=config, message_history=message_history) as host:
                await host.process_query(query)


def _get_editor_input(config):
    """Open a temporary file in the user's preferred editor and return the content."""

    with tempfile.NamedTemporaryFile(suffix=".md", mode="w+") as tf:
        # Write initial instructions to the file
        tf.write("# Enter your query below. Lines starting with # will be ignored.\n\n")
        tf.flush()

        # Open the editor
        subprocess.call([config.editor, tf.name])

        # Read the content
        tf.seek(0)
        content = tf.read()

    # Filter out comment lines and empty lines
    lines = [line for line in content.split("\n") if not line.startswith("#")]
    return "\n".join(lines)


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
