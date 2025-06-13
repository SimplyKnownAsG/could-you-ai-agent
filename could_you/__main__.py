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
        # Write message history to the file
        with MessageHistory(config.root) as message_history:
            for message in message_history.messages:
                tf.write(f"*** {message.role} ***\n")
                for content in message.content:
                    for key, val in vars(content).items():
                        tf.write(f"    {key}:\n")
                        if isinstance(val, str):
                            for line in val.splitlines():
                                tf.write(f"        {line}\n")
                        elif isinstance(val, (dict, list, _Dynamic)):
                            # Pretty print JSON with consistent indentation
                            v = val.to_dict() if isinstance(val, _Dynamic) else val
                            json_lines = json.dumps(v, indent=2).splitlines()
                            for line in json_lines:
                                tf.write(f"        {line}\n")
                        else:
                            # For other types, convert to string
                            tf.write(f"        {str(val)}\n")
                tf.write("\n")

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
