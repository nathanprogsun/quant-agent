from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.runs.manager import MultitaskStrategy, RunRecord
from app.common.runs.schemas import DisconnectMode

MAX_MESSAGES = 50
MAX_MESSAGE_LENGTH = 32768  # 32KB


class ThreadResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str | None = None
    model_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ThreadListResponse(BaseModel):
    threads: list[ThreadResponse]


class UpdateTitleRequest(BaseModel):
    title: str


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

    def from_run_record(record: RunRecord) -> Self:
        return RunResponse(
            run_id=record.run_id,
            thread_id=record.thread_id,
            user_id=record.user_id,
            status=record.status.value,
            model_name=record.model_name,
            assistant_id=record.assistant_id,
            metadata=record.metadata,
            on_disconnect=record.on_disconnect,
            multitask_strategy=record.multitask_strategy,
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class RunListResponse(BaseModel):
    runs: list[RunResponse]


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
        default_factory=lambda: ["values"],
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
