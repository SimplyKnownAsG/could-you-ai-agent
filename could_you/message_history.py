import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .logging_config import LOGGER
from .message import Message


class MessageHistory:
    path: Path
    messages: list[Message]
    enable: bool

    def __init__(self, root: Path, *, enable: bool = True):
        self.path = root / ".could-you-messages.json"
        self.messages = []
        self.enable = enable

    def __enter__(self):
        if self.enable:
            if self.path.exists():
                with open(self.path) as f:
                    self.messages = [Message(m) for m in json.load(f)]
                LOGGER.debug("Message history loaded")
            else:
                LOGGER.debug("Message history could not be found")
        else:
            LOGGER.debug("Message history disabled, not attempting to load")

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.enable:
            with open(self.path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)

    def add(self, message: Message):
        self.messages.append(message)
        message.print(info=LOGGER.info, debug=LOGGER.debug)

    def to_dict(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.messages]

    def print_history(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        """Print message history in a detailed format.

        Args:
            file: Optional file-like object to write to. If None, writes to sys.stdout
        """
        for message in self.messages:
            message.print(info=info, debug=debug)
