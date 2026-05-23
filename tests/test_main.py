import sys

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
