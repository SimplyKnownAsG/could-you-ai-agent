import argparse
import asyncio
import subprocess
import tempfile

from .agent import Agent
from .config import load
from .cy_error import CYError
from .logging_config import LOGGER, set_up_logging
from .message_history import MessageHistory
from .session import SessionManager


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Set up logging based on command line arguments
    if args.verbose:
        log_level = "DEBUG"
    elif args.quiet:
        log_level = "WARNING"
    else:
        log_level = "INFO"

    # Initialize logging
    set_up_logging(log_level)

    try:
        asyncio.run(amain(parser, args))
    except CYError as e:
        if not args.verbose:
            LOGGER.error("Use verbose mode to get stack trace")

        LOGGER.error(f"Failed with error (fault_owner:{e.fault_owner}): {e}", exc_info=args.verbose)
    except Exception as e:
        if not args.verbose:
            LOGGER.error("Use verbose mode to get stack trace")

        LOGGER.error(f"Failed with internal error: {e}", exc_info=args.verbose)


def create_parser():
    parser = argparse.ArgumentParser(description="Could-You MCP CLI")

    # Logging options (mutually exclusive)
    log_group = parser.add_mutually_exclusive_group()
    log_group.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output (DEBUG level logging)")
    log_group.add_argument("-q", "--quiet", action="store_true", help="Enable quiet mode (WARNING level logging only)")
    parser.add_argument("-H", "--no-history", action="store_true", help="Ignore message history")

    # Define a mutually exclusive group
    cmd_group = parser.add_mutually_exclusive_group()

    cmd_group.add_argument("query", nargs="?", help="A question or request to process")
    cmd_group.add_argument("-l", "--list-sessions", action="store_true", help="List existing sessions")
    cmd_group.add_argument("-i", "--init-session", action="store_true", help="Initialize a session in this directory")
    cmd_group.add_argument("-d", "--delete-session", metavar="session_path", help="Delete a specific session")
    cmd_group.add_argument("-p", "--print-history", action="store_true", help="Print the message history")
    cmd_group.add_argument("-t", "--test-connect", action="store_true", help="Test connection, and stop")
    cmd_group.add_argument(
        "-s",
        "--script",
        metavar="SCRIPT",
        help="Run an ephemeral stateless script from $XDG_CONFIG_HOME/could-you/script.<script>.json",
    )

    return parser


async def amain(parser, args):
    with SessionManager() as session_manager:
        if args.list_sessions:
            # List all sessions
            session_manager.list()
        elif args.init_session:
            # Create or switch to a session
            session_manager.init_session()
        elif args.delete_session:
            # Create or switch to a session
            session_manager.delete_session(args.delete_session)
        elif args.print_history:
            # Print message history
            config = session_manager.load_session()
            with MessageHistory(config.root) as message_history:
                message_history.print_history(info=LOGGER.info, debug=LOGGER.debug)
        elif args.test_connect:
            # List servers and their tools
            config = session_manager.load_session()
            with MessageHistory(config.root, enable=False) as message_history:
                async with Agent(config=config, message_history=message_history) as agent:
                    pass
        else:
            enable_history = not args.no_history

            if args.script:
                enable_history = False
                config = load(script_name=args.script)
            else:
                config = session_manager.load_session()

            query = args.query if args.query else config.query if config.query else _get_editor_input(config)

            if not query:
                LOGGER.warning("no input provided")
                parser.print_help()
                return

            with MessageHistory(config.root, enable=enable_history) as message_history:
                async with Agent(config=config, message_history=message_history) as agent:
                    await agent.orchestrate(query)


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


if __name__ == "__main__":
    main()
