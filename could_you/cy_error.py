from enum import Enum


class FaultOwner(Enum):
    INTERNAL = "INTERNAL"
    LLM = "LLM"
    USER = "USER"
    MCP_SERVER = "MCP_SERVER"


class CYError(Exception):
    def __init__(self, *, message, retriable: bool, fault_owner: FaultOwner):
        super().__init__(message)
        self.retriable = retriable
        self.fault_owner = fault_owner
