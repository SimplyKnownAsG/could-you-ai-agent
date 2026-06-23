import sys

import pytest

from could_you.__main__ import create_parser


def test_dialogue_cli_flags_default_to_none(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you"])

    args = parser.parse_args()

    assert args.dialogue_load is None
    assert args.dialogue_store is None


def test_dialogue_cli_flags_support_short_positive_shorthands(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "-L", "-S"])

    args = parser.parse_args()

    assert args.dialogue_load is True
    assert args.dialogue_store is True


def test_dialogue_cli_flags_support_long_positive_overrides(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "--dialogue-load", "--dialogue-store"])

    args = parser.parse_args()

    assert args.dialogue_load is True
    assert args.dialogue_store is True


def test_dialogue_cli_flags_support_long_negative_overrides(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "--no-dialogue-load", "--no-dialogue-store"])

    args = parser.parse_args()

    assert args.dialogue_load is False
    assert args.dialogue_store is False


def test_query_flag_populates_query(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "--query", "hello"])

    args = parser.parse_args()

    assert args.query == "hello"


@pytest.mark.parametrize(
    ("argv", "command", "subcommand", "expected"),
    [
        (["could-you", "script", "git-commit"], "script", None, "git-commit"),
        (["could-you", "s", "git-commit"], "script", None, "git-commit"),
        (["could-you", "workspace", "init"], "workspace", "init", None),
        (["could-you", "workspace", "sync"], "workspace", "sync", None),
        (["could-you", "ws", "sync"], "workspace", "sync", None),
        (["could-you", "memory", "backup", "topic"], "memory", "backup", "topic"),
        (["could-you", "m", "backup", "topic"], "memory", "backup", "topic"),
        (["could-you", "memory", "inspect"], "memory", "inspect", None),
        (["could-you", "memory", "status"], "memory", "inspect", None),
        (["could-you", "memory", "search", "alpha", "beta"], "memory", "search", ["alpha", "beta"]),
        (["could-you", "session", "list"], "session", "list", None),
        (["could-you", "session", "delete", "/tmp/session"], "session", "delete", "/tmp/session"),
        (["could-you", "dialogue", "print"], "dialogue", "print", None),
        (["could-you", "permissions"], "permissions", None, None),
        (["could-you", "test", "connect", "ping"], "test", "connect", "ping"),
        (["could-you", "--query", "hello"], None, None, None),
    ],
)
def test_subcommand_parsing(monkeypatch, argv, command, subcommand, expected):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", argv)

    args = parser.parse_args()

    assert args.command == command

    if argv[1:3] == ["--query", "hello"]:
        assert args.query == "hello"
        return

    if command == "script":
        assert args.script_name == expected
    elif command == "workspace":
        assert args.workspace_command == subcommand
    elif command == "memory":
        assert args.memory_command == subcommand
        if subcommand == "backup":
            assert args.topic == expected
        elif subcommand == "search":
            assert args.terms == expected
    elif command == "session":
        assert args.session_command == subcommand
        if subcommand == "delete":
            assert args.session_path == expected
    elif command == "dialogue":
        assert args.dialogue_command == subcommand
    elif command == "test":
        assert args.test_command == subcommand
        if subcommand == "connect":
            assert args.message == expected
