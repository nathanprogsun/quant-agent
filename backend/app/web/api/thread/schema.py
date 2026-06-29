from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.common.runs.manager import MultitaskStrategy, RunRecord
from app.common.runs.schemas import DisconnectMode
from app.core.chat.service.stream_modes import DEFAULT_STREAM_MODES

MAX_MESSAGES = 50
MAX_MESSAGE_LENGTH = 32768  # 32KB


class RunInput(BaseModel):
    """Input payload for a run — wraps a list of messages."""

    model_config = ConfigDict(extra="ignore")

    messages: list["MessageInput"] = Field(default_factory=list)


class RunRequestConfig(BaseModel):
    """Typed wrapper for the ``config`` field of a run request."""

    model_config = ConfigDict(extra="ignore")

    configurable: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    recursion_limit: int | None = Field(default=None, ge=1)
    tags: list[str] | None = None


class RunEventPayload(BaseModel):
    """SSE event payload emitted to clients.

    The data side of an SSE event is intentionally permissive (the LangGraph
    SDK emits heterogeneous shapes for messages, values, state, etc.), so
    we accept arbitrary JSON-compatible dicts.
    """

    model_config = ConfigDict(extra="ignore")

    data: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None
    event: str | None = None


class ThreadResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str | None = None
    model_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def thread_id(self) -> UUID:
        """LangGraph SDK expects ``thread_id`` alongside legacy ``id``."""
        return self.id


class ThreadListResponse(BaseModel):
    threads: list[ThreadResponse]


class UpdateTitleRequest(BaseModel):
    title: str


class CreateThreadRequest(BaseModel):
    """Request body for creating a thread.

    Accepts both snake_case (``thread_id``, ``model_name``) and the LangGraph
    SDK camelCase alias (``threadId``). When both ``thread_id`` and
    ``threadId`` are provided, ``threadId`` (SDK) wins to match SDK
    expectations. If neither is given, the service generates a UUID.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    thread_id: UUID | None = Field(default=None, validation_alias="thread_id")
    threadId: UUID | None = Field(default=None, validation_alias="threadId")
    title: str | None = None
    model_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _merge_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if data.get("threadId") and not data.get("thread_id"):
            data["thread_id"] = data["threadId"]
        return data

    @property
    def resolved_thread_id(self) -> UUID | None:
        """Return whichever alias the caller actually sent."""
        return self.thread_id or self.threadId


class RunResponse(BaseModel):
    run_id: UUID
    thread_id: UUID
    user_id: UUID
    status: str
    model_name: str | None = None
    assistant_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    on_disconnect: DisconnectMode
    multitask_strategy: MultitaskStrategy
    error: str | None = None
    created_at: str
    updated_at: str

    @staticmethod
    def from_run_record(record: RunRecord) -> "RunResponse":
        return RunResponse(
            run_id=record.run_id,
            thread_id=record.thread_id,
            user_id=record.user_id,
            status=record.status.value,
            model_name=record.model_name,
            assistant_id=record.assistant_id,
            metadata=record.metadata,
            on_disconnect=record.on_disconnect,
            multitask_strategy=MultitaskStrategy(record.multitask_strategy),
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class RunListResponse(BaseModel):
    runs: list[RunResponse]


class CancelResponse(BaseModel):
    status: str
    run_id: UUID


class MessageInput(BaseModel):
    """Accept both backend format (role) and LangChain SDK format (type)."""

    model_config = ConfigDict(populate_by_name=True)

    role: Literal["user", "assistant", "system"] = Field(
        default="user",
        validation_alias="role",
    )
    type: Literal["human", "ai", "system", "tool"] = Field(
        default="human",
        validation_alias="type",
    )
    content: str = Field(..., max_length=MAX_MESSAGE_LENGTH)

    @field_validator("role", "type", mode="before")
    @classmethod
    def _normalize_role_type(cls, v: Any, info: Any) -> Any:
        """Normalize role/type: accept both formats, prefer the non-null one."""
        if v is None:
            return v
        # If the field name matches the incoming key, use it directly
        # Otherwise let the other field handle it
        return v


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    input: dict[str, Any] = Field(
        default_factory=lambda: {"messages": []},
        description="包含 messages 数组的输入",
    )
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    stream_mode: list[str] = Field(
        default_factory=lambda: list(DEFAULT_STREAM_MODES),
        validation_alias="streamMode",
    )
    on_disconnect: DisconnectMode = Field(
        default=DisconnectMode.CANCEL,
        validation_alias="onDisconnect",
    )
    multitask_strategy: MultitaskStrategy = Field(
        default=MultitaskStrategy.REJECT,
        validation_alias="multitaskStrategy",
    )

    @field_validator("on_disconnect", mode="before")
    @classmethod
    def normalize_on_disconnect(cls, v: Any) -> Any:
        """Accept LangGraph SDK alias ``continue`` for keep-alive runs."""
        if v == "continue":
            return DisconnectMode.CONTINUE.value
        return v

    @field_validator("input")
    @classmethod
    def validate_input_messages(cls, v: dict[str, Any]) -> dict[str, Any]:
        messages = v.get("messages", [])
        if len(messages) > MAX_MESSAGES:
            raise ValueError(f"messages 数组长度不能超过 {MAX_MESSAGES}")
        return v

    @field_validator("stream_mode", mode="before")
    @classmethod
    def normalize_stream_mode(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [v]
        return v


class HistoryRequest(BaseModel):
    """LangGraph SDK POST /history body."""

    model_config = ConfigDict(populate_by_name=True)

    limit: int = Field(default=10, ge=1, le=1000)
    before: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None


class StateUpdateRequest(BaseModel):
    """LangGraph SDK POST /state body."""

    model_config = ConfigDict(populate_by_name=True)

    values: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None
    checkpoint_id: str | None = Field(default=None, validation_alias="checkpointId")
    as_node: str | None = Field(default=None, validation_alias="asNode")


# Resolve the forward reference to MessageInput (defined above in this module).
RunInput.model_rebuild()
