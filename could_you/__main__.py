import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path

import yaml
from cattrs import Converter

from .agent import Agent
from .config import _find_workspace_config_dir, load
from .cy_error import CYError
from .dialogue import Dialogue
from .inspect_memory import dump_memory_inspection_yaml, inspect_memory
from .logging_config import LOGGER, set_up_logging
from .memory import backup_dialogue
from .memory.search import search_memory
from .permissions import format_permission_report, inspect_permission_boundary
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
    parser.add_argument(
        "-L",
        "--dialogue-load",
        dest="dialogue_load",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override whether existing dialogue is loaded for this run",
    )
    parser.add_argument(
        "-S",
        "--dialogue-store",
        dest="dialogue_store",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override whether dialogue is stored after this run",
    )
    parser.add_argument(
        "-C",
        "--dump-config",
        nargs="?",
        const="json",
        choices=["json", "yaml"],
        default=None,
        help="Print the effective configuration as JSON (default) or YAML, then exit",
    )
    parser.add_argument(
        "--query",
        dest="query",
        help="A question or request to process",
    )
    parser.add_argument(
        "-s",
        "--script",
        metavar="SCRIPT",
        help="Run a skill from the config directory (e.g., script.<name>.json). Statefulness is determined by the skill's config.",
    )
    subparsers = parser.add_subparsers(dest="command")

    workspace_parser = subparsers.add_parser("workspace", aliases=["ws"], help="Workspace-related commands")
    workspace_subparsers = workspace_parser.add_subparsers(dest="workspace_command")

    workspace_init_parser = workspace_subparsers.add_parser(
        "init", help="Initialize a .could-you workspace in this directory"
    )
    workspace_init_parser.set_defaults(command="workspace", workspace_command="init")

    workspace_sync_parser = workspace_subparsers.add_parser(
        "sync", help="Sync managed workspace templates into .could-you"
    )
    workspace_sync_parser.set_defaults(command="workspace", workspace_command="sync")

    memory_parser = subparsers.add_parser("memory", aliases=["m"], help="Memory-related commands")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")

    memory_backup_parser = memory_subparsers.add_parser(
        "backup", help="Back up dialogue to the private memory git repo"
    )
    memory_backup_parser.add_argument(
        "topic", nargs="?", default=None, help="Optional topic for the backup commit message"
    )
    memory_backup_parser.set_defaults(command="memory", memory_command="backup")

    memory_inspect_parser = memory_subparsers.add_parser(
        "inspect",
        aliases=["status"],
        help="Print a deterministic report about dialogue, prompt loads, thresholds, and memory files",
    )
    memory_inspect_parser.set_defaults(command="memory", memory_command="inspect")

    memory_search_parser = memory_subparsers.add_parser("search", help="Search durable memory for one or more terms")
    memory_search_parser.add_argument("terms", nargs="+", metavar="TERM", help="Search terms")
    memory_search_parser.set_defaults(command="memory", memory_command="search")

    session_parser = subparsers.add_parser("session", help="Session-related commands")
    session_subparsers = session_parser.add_subparsers(dest="session_command")

    session_list_parser = session_subparsers.add_parser("list", help="List existing sessions")
    session_list_parser.set_defaults(command="session", session_command="list")

    session_delete_parser = session_subparsers.add_parser("delete", help="Delete a specific session")
    session_delete_parser.add_argument("session_path", help="Session path to delete")
    session_delete_parser.set_defaults(command="session", session_command="delete")

    dialogue_parser = subparsers.add_parser("dialogue", help="Dialogue-related commands")
    dialogue_subparsers = dialogue_parser.add_subparsers(dest="dialogue_command")

    dialogue_print_parser = dialogue_subparsers.add_parser("print", help="Print the dialogue history")
    dialogue_print_parser.set_defaults(command="dialogue", dialogue_command="print")

    permissions_parser = subparsers.add_parser(
        "permissions",
        help="Print an observational report about the current OS-user/filesystem permission boundary",
    )
    permissions_parser.set_defaults(command="permissions")

    test_parser = subparsers.add_parser("test", help="Connectivity and validation commands")
    test_subparsers = test_parser.add_subparsers(dest="test_command")

    test_connect_parser = test_subparsers.add_parser("connect", help="Test connection, send a message to LLM, and stop")
    test_connect_parser.add_argument("message", nargs="?", default="Say hi", help="Test message to send")
    test_connect_parser.set_defaults(command="test", test_command="connect")

    parser.add_argument(
        "--format",
        default="json",
        choices=["json", "yaml"],
        help="Output format for search results",
    )

    return parser


async def amain(parser, args):
    query = args.query

    # Early config dump
    if args.dump_config:
        config = load(args.script)[0]
        converter = Converter(use_alias=True)
        config_dict = converter.unstructure(config)

        if args.dump_config == "yaml":
            print(yaml.safe_dump(config_dict, sort_keys=False, default_flow_style=False))  # noqa: T201
        else:
            print(json.dumps(config_dict, indent=2))  # noqa: T201

        return

    with SessionManager() as session_manager:
        if args.command == "workspace" and args.workspace_command == "init":
            session_manager.init_session()
        elif args.command == "workspace" and args.workspace_command == "sync":
            session_manager.sync_workspace()
        elif args.command == "session" and args.session_command == "list":
            session_manager.list()
        elif args.command == "session" and args.session_command == "delete":
            session_manager.delete_session(args.session_path)
        elif args.command == "dialogue" and args.dialogue_command == "print":
            session = session_manager.load_session(None)
            with session.dialogue(load=True, store=False) as dialogue:
                dialogue.print(info=LOGGER.info, debug=LOGGER.debug)
        elif args.command == "memory" and args.memory_command == "backup":
            w_config_dir = _find_workspace_config_dir(Path.cwd())
            result = backup_dialogue(w_config_dir, topic=args.topic)
            LOGGER.info(f"Memory repo: {result.repo_path}")
            LOGGER.info(f"Backup file: {result.backup_path}")
        elif args.command == "memory" and args.memory_command == "inspect":
            print(dump_memory_inspection_yaml(inspect_memory(args.script)))  # noqa: T201
        elif args.command == "permissions":
            w_config_dir = _find_workspace_config_dir(Path.cwd())
            report = inspect_permission_boundary(w_config_dir)
            print(format_permission_report(report))  # noqa: T201
        elif args.command == "memory" and args.memory_command == "search":
            results = search_memory(args.terms)
            if results is not None:
                if not results:
                    return

                if args.format == "yaml":
                    print(yaml.safe_dump(results, sort_keys=False, default_flow_style=False))  # noqa: T201
                else:
                    print(json.dumps(results, indent=2))  # noqa: T201
        elif args.command == "test" and args.test_command == "connect":
            session = session_manager.load_session(None)
            with session.dialogue(load=False, store=False) as dialogue:
                async with Agent(config=session.config, dialogue=dialogue) as agent:
                    await agent.orchestrate(args.message)
        else:
            session = session_manager.load_session(args.script)

            dialogue_load = session.config.dialogue.load if args.dialogue_load is None else args.dialogue_load
            dialogue_store = session.config.dialogue.store if args.dialogue_store is None else args.dialogue_store

            query = (
                query
                if query
                else session.config.query
                if session.config.query
                else _get_editor_input(session.w_config_dir)
            )

            if not query:
                LOGGER.warning("no input provided")
                parser.print_help()
                return

            with session.dialogue(load=dialogue_load, store=dialogue_store) as dialogue:
                async with Agent(config=session.config, dialogue=dialogue) as agent:
                    await agent.orchestrate(query)
                    _remove_query_md(session.w_config_dir)


MARKER = "# *** PROVIDE_INPUT_AFTER_THIS_LINE ***"


def _get_editor_input(w_config_dir: Path):
    """Open a temporary file in the user's preferred editor and return the content."""
    query_md_path = w_config_dir / "query.md"
    existing_query = _load_query(query_md_path)

    with query_md_path.open("w") as tf:
        tf.write("# Previous dialogue\n\n")
        # Write dialogue history to the file
        with Dialogue(w_config_dir, load=True, store=False) as dialogue:

            def printer(msg):
                print(msg, file=tf)

            dialogue.print(info=printer, debug=printer)

        # Write the special editor input marker - this exact line is used to find user input
        tf.write(f"\n{MARKER}\n\n")
        tf.write(existing_query)
        tf.flush()

    # Open the editor
    editor = os.environ.get("EDITOR", "vim")
    subprocess.call([editor, tf.name])

    return _load_query(query_md_path)


def _load_query(query_md_path: Path):
    if not query_md_path.exists():
        return ""

    content = query_md_path.read_text()
    lines = content.splitlines(keepends=True)

    for i, line in enumerate(lines):
        if line == MARKER + "\n":
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


def _remove_query_md(w_config_dir: Path):
    query_md_path = w_config_dir / "query.md"
    query_md_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
