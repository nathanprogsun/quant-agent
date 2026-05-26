"""Run status and disconnect mode enums."""

from enum import StrEnum


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"


class DisconnectMode(StrEnum):
    CANCEL = "cancel"
    CONTINUE = "keep_alive"  # Avoids Python keyword "continue"
