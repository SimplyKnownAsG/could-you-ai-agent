import json
import sys
from pathlib import Path
from typing import List, Dict, Any

from .message import Message, _Dynamic


class MessageHistory:
    path: Path
    messages: List[Message]

    def __init__(self, root: Path):
        self.path = root / ".could-you-messages.json"
        self.messages = []

    def __enter__(self):
        if self.path.exists():
            with open(self.path, "r") as f:
                self.messages = [Message(m) for m in json.load(f)]

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        with open(self.path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def add(self, message: Message, verbose=False):
        self.messages.append(message)
        message.print(verbose=verbose)

    def to_dict(self) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self.messages]

    def print_history(self, file=None, verbose=False):
        """Print message history in a detailed format.

        Args:
            file: Optional file-like object to write to. If None, writes to sys.stdout
            verbose: Whether to show verbose output including tool details
        """
        output = file if file is not None else sys.stdout

        for message in self.messages:
            message.print(output, verbose=verbose)