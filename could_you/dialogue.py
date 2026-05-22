import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cattrs import Converter

from .logging_config import LOGGER
from .message import Message

converter = Converter(use_alias=True, omit_if_default=True)


class Dialogue:
    path: Path
    messages: list[Message]
    load: bool
    store: bool

    def __init__(self, w_config_dir: Path, *, load: bool = True, store: bool = True):
        self.path = w_config_dir / "dialogue.json"
        self.messages = []
        self.load = load
        self.store = store

    def __enter__(self):
        if self.load:
            if self.path.exists():
                with open(self.path) as f:
                    self.messages = [converter.structure(m, Message) for m in json.load(f)]
                LOGGER.debug("Dialogue loaded")
            else:
                LOGGER.debug("Dialogue could not be found")
        else:
            LOGGER.debug("Dialogue loading disabled, not attempting to load")

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.store:
            with open(self.path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
        else:
            LOGGER.debug("Dialogue storage disabled, not writing dialogue")

    def add(self, message: Message):
        self.messages.append(message)
        message.print(info=LOGGER.info, debug=LOGGER.debug)

    def to_dict(self) -> list[dict[str, Any]]:
        return [converter.unstructure(m) for m in self.messages]

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        """Print the dialogue in a detailed format."""
        for message in self.messages:
            message.print(info=info, debug=debug)
