from dotenv import load_dotenv
import asyncio
import argparse
from .session_manager import SessionManager
from .mcp_client import MCPClient
import sys
from .config import load


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
        "-c", "--clear-sessions", action="store_true", help="Clear existing sessions"
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
        session_manager.init_session()
    elif args.delete_session:
        # Create or switch to a session
        session_manager.delete_session(args.delete_session)
    elif args.clear_sessions:
        # Create or switch to a session
        session_manager.clear_sessions()
    elif not args.query:
        parser.print_help()
    else:
        config = load()
        # Handle a user query
        print(f"GRAHAM here")
        session = None  # session_manager.get_current_session()
        if session:
            print(f"Processing query in session: {session['name']}")
            # Here, you would process the query and return a response
            print(f"Query: {args.query}")

        # client = MCPClient(servers=servers)
        async with MCPClient(servers=config.servers) as client:
            await client.chat_loop(args.query)


def main():
    load_dotenv()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
