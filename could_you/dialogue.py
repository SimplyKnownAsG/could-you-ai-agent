import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any

from cattrs import Converter

from .config import DialogueProps
from .logging_config import LOGGER
from .message import Message, MessageType, TextContent

converter = Converter(use_alias=True, omit_if_default=True)


class Dialogue:
    props: DialogueProps
    path: Path
    messages: list[Message]
    _file_handle: IO | None = None

    def __init__(
        self,
        w_config_dir: Path,
        *,
        props: DialogueProps | None = None,
    ):
        self.props = props or DialogueProps()
        suffix = props.name
        if suffix:
            suffix = "-" + suffix
        self.path = w_config_dir / f"dialogue{suffix}.jsonl"
        self.messages = []

    def __enter__(self):
        if self.props.load:
            if self.path.exists():
                with open(self.path) as f:
                    self.messages = [converter.structure(json.loads(line), Message) for line in f if line.strip()]
                LOGGER.debug("Dialogue loaded from %s", self.path)
            else:
                LOGGER.debug("Dialogue file could not be found at %s", self.path)
        else:
            LOGGER.debug("Dialogue loading disabled, not attempting to load")

        if self.props.store:
            # Open the file in append mode and keep it open for the life of the context
            self._file_handle = open(self.path, "a")

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        if not self.props.store:
            LOGGER.debug("Dialogue storage disabled, not writing dialogue")

    def add(self, message: Message):
        if message.role == "user":
            now = datetime.now().astimezone()
            tz_name = now.strftime("%Z")
            datetime_str = now.strftime("%Y-%m-%dT%H:%M")
            monday = now.date() - timedelta(days=now.weekday())
            week_of = f"{monday.strftime('%A, %B')} {monday.day}"
            date_message = f"The current time is {datetime_str} {tz_name}, the week of {week_of}."
            sys_message = Message(
                role="system",
                content=[TextContent(text=date_message, type="text")],
                type=MessageType.NORMAL,
            )
            self.messages.append(sys_message)
            self._store_message(sys_message)

        self.messages.append(message)
        message.print(info=LOGGER.info, debug=LOGGER.debug)
        self._store_message(message)

    def _store_message(self, message: Message):
        if self.props.store and self._file_handle:
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
