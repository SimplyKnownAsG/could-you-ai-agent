import argparse
import asyncio
import subprocess
import tempfile

from .agent import Agent
from .config import init, load
from .logging_config import LOGGER, setup_logging
from .message_history import MessageHistory
from .session_manager import SessionManager


async def amain():
    parser = argparse.ArgumentParser(description="Could-You MCP CLI")

    # Logging options (mutually exclusive)
    log_group = parser.add_mutually_exclusive_group()
    log_group.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output (DEBUG level logging)")
    log_group.add_argument("-q", "--quiet", action="store_true", help="Enable quiet mode (WARNING level logging only)")
    parser.add_argument("-H", "--no-history", action="store_true", help="Ignore message history")

    # Define a mutually exclusive group
    group = parser.add_mutually_exclusive_group()

    group.add_argument("query", nargs="?", help="A question or request to process")
    group.add_argument("-l", "--list-sessions", action="store_true", help="List existing sessions")
    group.add_argument("-i", "--init-session", action="store_true", help="Initialize a session in this directory")
    group.add_argument("-d", "--delete-session", metavar="session_path", help="Delete a specific session")
    group.add_argument("-p", "--print-history", action="store_true", help="Print the message history")
    group.add_argument("-t", "--test-connect", action="store_true", help="Test connection, and stop")

    args = parser.parse_args()

    # Set up logging based on command line arguments
    if args.verbose:
        log_level = "DEBUG"
    elif args.quiet:
        log_level = "WARNING"
    else:
        log_level = "INFO"

    # Initialize logging
    setup_logging(log_level)

    session_manager = SessionManager()

    if args.list_sessions:
        # List all sessions
        sessions = session_manager.list_sessions()
        for session in sessions:
            LOGGER.info(
                f"Session: {session['name']}, Tokens Used: {session['tokens_used']}, Directory: {session['directory']}"
            )
    elif args.init_session:
        # Create or switch to a session
        l_config_path = init()
        LOGGER.info(f"initialized config file: {l_config_path}")
    elif args.delete_session:
        # Create or switch to a session
        session_manager.delete_session(args.delete_session)
    elif args.print_history:
        # Print message history
        config = load()
        with MessageHistory(config.root) as message_history:
            message_history.print_history(info=LOGGER.info, debug=LOGGER.debug)
    elif args.test_connect:
        # List servers and their tools
        config = load()
        with MessageHistory(config.root, enable=False) as message_history:
            async with Agent(config=config, message_history=message_history) as host:
                pass
    else:
        config = load()
        query = args.query if args.query else _get_editor_input(config)

        if not query:
            LOGGER.warn("no imput provided")
            parser.print_help()
            return

        with MessageHistory(config.root, enable=not args.no_history) as message_history:
            async with Agent(config=config, message_history=message_history) as host:
                await host.orchestrate(query)


def _get_editor_input(config):
    """Open a temporary file in the user's preferred editor and return the content."""

    with tempfile.NamedTemporaryFile(suffix=".md", mode="w+") as tf:
        tf.write("# Previous messages\n\n")
        # Write message history to the file
        with MessageHistory(config.root) as message_history:

            def printer(msg):
                print(msg, file=tf)

            message_history.print_history(info=printer, debug=printer)

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
        if line == marker + "\n":
            input_lines = lines[i + 1 :]
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
