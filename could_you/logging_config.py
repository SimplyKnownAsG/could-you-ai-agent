import logging
import sys
from typing import Optional


class _TerseFormatter(logging.Formatter):
    """Custom formatter that uses single letter log levels"""

    LEVEL_MAP = {
        'DEBUG': 'D',
        'INFO': 'I',
        'WARNING': 'W',
        'ERROR': 'E',
        'CRITICAL': 'C'
    }

    def format(self, record):
        # Replace the levelname with single letter
        original_levelname = record.levelname
        record.levelname = self.LEVEL_MAP.get(original_levelname, original_levelname[0])

        # Format the message
        formatted = super().format(record)

        # Restore original levelname
        record.levelname = original_levelname

        return formatted


def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """
    Set up logging configuration for the could-you application.

    Args:
        level: Log level string ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
               If None, defaults to 'INFO'

    Returns:
        Logger instance configured for the application
    """
    # Default to INFO if no level specified
    if level is None:
        level = 'INFO'

    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger('could_you')
    logger.setLevel(numeric_level)

    # Remove any existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    # Create terse formatter
    formatter = _TerseFormatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    # Prevent propagation to root LOGGER to avoid duplicate messages
    logger.propagate = False

    return logger

LOGGER = logging.getLogger('could_you')
