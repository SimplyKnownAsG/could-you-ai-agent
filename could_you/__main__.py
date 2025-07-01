import asyncio
import argparse
import tempfile
import subprocess
import json
from .session_manager import SessionManager
from .mcp_host import MCPHost
from .config import load, init
from .message_history import MessageHistory
from .message import _Dynamic


async def amain():
    parser = argparse.ArgumentParser(description="Could-You MCP CLI")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output mode")

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
    group.add_argument(
        "-p", "--print-history", action="store_true", help="Print the message history"
    )
    group.add_argument(
        "-t", "--test-connect", action="store_true", help="Test connection, and stop"
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
    elif args.print_history:
        # Print message history
        config = load()
        with MessageHistory(config.root) as message_history:
            message_history.print_history(verbose=args.verbose)
    elif args.test_connect:
        # List servers and their tools
        config = load()
        with MessageHistory(config.root) as message_history:
            async with MCPHost(config=config, message_history=message_history) as host:
                pass
    else:
        config = load()
        query = args.query if args.query else _get_editor_input(config, args.verbose)

        if not query:
            parser.print_help()
            return

        with MessageHistory(config.root) as message_history:
            async with MCPHost(config=config, message_history=message_history) as host:
                await host.process_query(query, verbose=args.verbose)


def _get_editor_input(config, verbose=False):
    """Open a temporary file in the user's preferred editor and return the content."""

    with tempfile.NamedTemporaryFile(suffix=".md", mode="w+") as tf:
        # Write message history to the file
        with MessageHistory(config.root) as message_history:
            message_history.print_history(tf, verbose=verbose)

        # Write the special editor input marker - this exact line is used to find user input
        marker = "# *** PROVIDE_INPUT_AFTER_THIS_LINE ***"
        tf.write(f"\n{marker}\n\n")
        tf.flush()

        # Open the editor
        subprocess.call([config.editor, tf.name])

        # Read the content
        tf.seek(0)
        content = tf.read()

    # Split content at the marker line, looking for complete lines only
    lines = content.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line == marker+"\n":
            input_lines = lines[i+1:]
            break
    else:
        input_lines = lines

    # Trim empty lines from start
    while input_lines and input_lines[0].strip() == "":
        input_lines.pop(0)

    # Trim empty lines from end
    while input_lines and input_lines[-1].strip() == "":
        input_lines.pop()

    return "".join(input_lines)


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
