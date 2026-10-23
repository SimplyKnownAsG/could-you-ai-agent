"""Tests for the tag module - specifically testing the system_message function.

This tests support for OpenAI's limitation of allowing only one system message, which is handled by wrapping additional "system" content in tags and converting those messages to user role with preserved tags."""

from could_you import tag


def test_system_message_wraps_text_correctly():
    """Test that system_message wraps input with correct tags."""
    message = "Hello, world!"
    result = tag.system_message(message)

    assert result == "<could-you-system-message>\nHello, world!\n</could-you-system-message>"


def test_system_message_preserves_newlines():
    """Test that system_message preserves newlines in the input."""
    message = "Line 1\nLine 2\nLine 3"
    result = tag.system_message(message)

    # Newlines should be preserved exactly as-is
    assert message in result


def test_system_message_handles_empty_string():
    """Test that system_message handles an empty string."""
    message = ""
    result = tag.system_message(message)

    assert result == "<could-you-system-message>\n\n</could-you-system-message>"
