import logging
import sys
from typing import ClassVar


class _TerseFormatter(logging.Formatter):
    """Custom formatter that uses single letter log levels"""

    LEVEL_MAP: ClassVar[dict] = {"DEBUG": "D", "INFO": "I", "WARNING": "W", "ERROR": "E", "CRITICAL": "C"}

    def format(self, record):
        original_levelname = record.levelname
        record.levelname = self.LEVEL_MAP.get(original_levelname, original_levelname[0])
        formatted = super().format(record)
        record.levelname = original_levelname
        return formatted


class _CliFormatter(logging.Formatter):
    """A formatter that shows the message only for INFO, and full details for other levels."""

    TERSE_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
    DEBUG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.info_formatter = logging.Formatter("%(message)s")
        self.terse_formatter = _TerseFormatter(self.TERSE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
        self.debug_formatter = _TerseFormatter(self.DEBUG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record):
        if record.levelno == logging.INFO:
            return self.info_formatter.format(record)
        if record.levelno == logging.DEBUG:
            return self.debug_formatter.format(record)
        return self.terse_formatter.format(record)


def set_up_logging(level: str | None = None) -> logging.Logger:
    """
    Set up logging configuration for the could-you application.
    """
    if level is None:
        level = "INFO"

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logger = logging.getLogger("could_you")
    logger.setLevel(numeric_level)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    formatter = _CliFormatter()
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.propagate = False

    return logger


LOGGER = logging.getLogger("could_you")
