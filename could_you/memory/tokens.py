from ..config import MemoryProps
from ..message import Message


def current_token_percent_used(messages: list[Message]) -> float | None:
    for message in reversed(messages):
        if not message.metadata:
            continue

        percent_used = message.metadata.percent_used()
        if percent_used is not None:
            return percent_used

    return None


def should_warn(percent_used: float | None, memory: MemoryProps) -> bool:
    if percent_used is None:
        return False

    return percent_used >= memory.warning_threshold_percent


def should_reject(percent_used: float | None, memory: MemoryProps) -> bool:
    if percent_used is None:
        return False

    return percent_used >= memory.rejection_threshold_percent
