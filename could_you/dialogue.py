import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, IO

from cattrs import Converter

from .config import DialogueProps
from .logging_config import LOGGER
from .message import Message

converter = Converter(use_alias=True, omit_if_default=True)


class Dialogue:
    path: Path
    messages: list[Message]
    load: bool
    store: bool
    _file_handle: IO | None = None

    def __init__(
        self,
        w_config_dir: Path,
        *,
        props: DialogueProps | None = None,
        load: bool | None = None,
        store: bool | None = None,
    ):
        props = props or DialogueProps()
        self.path = w_config_dir / "dialogue.jsonl"
        self.messages = []
        self.load = props.load if load is None else load
        self.store = props.store if store is None else store

    def __enter__(self):
        if self.load:
            if self.path.exists():
                with open(self.path) as f:
                    for line in f:
                        if line.strip():
                            self.messages.append(converter.structure(json.loads(line), Message))
                LOGGER.debug("Dialogue loaded from %s", self.path)
            else:
                LOGGER.debug("Dialogue file could not be found at %s", self.path)
        else:
            LOGGER.debug("Dialogue loading disabled, not attempting to load")

        if self.store:
            # Open the file in append mode and keep it open for the life of the context
            self._file_handle = open(self.path, "a")

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        if not self.store:
            LOGGER.debug("Dialogue storage disabled, not writing dialogue")

    def add(self, message: Message):
        self.messages.append(message)
        message.print(info=LOGGER.info, debug=LOGGER.debug)

        if self.store and self._file_handle:
            json_str = json.dumps(converter.unstructure(message))
            self._file_handle.write(json_str + "\n")
            self._file_handle.flush()

    def to_dict(self) -> list[dict[str, Any]]:
        return [converter.unstructure(m) for m in self.messages]

    def print(self, *, info: Callable[[str], None] | None = None, debug: Callable[[str], None] | None = None):
        """Print the dialogue in a detailed format."""
        info = info or LOGGER.info
        debug = debug or LOGGER.debug
        for message in self.messages:
            message.print(info=info, debug=debug)
