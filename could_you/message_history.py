import json
from pathlib import Path
from typing import List, Dict, Any

from .message import Message


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

    def add(self, message: Message):
        self.messages.append(message)
        print(f">>> *** {message.role} *** ===")

        for content in message.content:
            for key, val in vars(content).items():
                print(f"  {key}:")

                if key == "text":
                    for line in val.splitlines():
                        print("    " + line)
                else:
                    print(f"    <{key}>")

        print(f"<<< *** {message.role} *** ===")

    def to_dict(self) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self.messages]
