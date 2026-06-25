"""Pydantic schemas for jq_kb chunks and manifests."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Library(StrEnum):
    JQ_API = "jq_api"
    JQ_DICT = "jq_dict"
    JQ_STRATEGY = "jq_strategy"


class Source(StrEnum):
    JQ_OFFICIAL_DOC = "jq_official_doc"
    JQ_COMMUNITY = "jq_community_post"
    LOCAL_2020_2024 = "local_2020_2024"


class JqApiEnvConstraint(StrEnum):
    RESEARCH = "research_env"
    BACKTEST = "backtest_env"
    TRADING = "trading_env"
    PAPER_TRADING = "paper_trading"
    ALL = "all"


def env_support_flags(env: list[JqApiEnvConstraint]) -> dict[str, str]:
    """Chroma-safe metadata flags for env filtering (EQ only, no CONTAINS).

    ChromaVectorStore does not support ``FilterOperator.CONTAINS`` on
    comma-separated strings, so each environment gets a ``"1"`` / ``"0"`` flag.
    """
    universal = JqApiEnvConstraint.ALL in env or not env
    return {
        f"supports_{constraint.value}": "1"
        if universal or constraint in env
        else "0"
        for constraint in JqApiEnvConstraint
        if constraint != JqApiEnvConstraint.ALL
    }


class JqApiChunk(BaseModel):
    id: str
    library: Literal[Library.JQ_API] = Library.JQ_API
    source: Literal[Source.JQ_OFFICIAL_DOC] = Source.JQ_OFFICIAL_DOC
    function_name: str
    module: str = ""
    signature: str
    params: list[dict[str, str]] = Field(default_factory=list)
    returns: str = ""
    env: list[JqApiEnvConstraint] = Field(default_factory=list)
    source_url: str
    content: str
    contextual_content: str
    examples: list[str] = Field(default_factory=list)
    ingested_at: date = Field(default_factory=date.today)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "library": self.library.value,
            "function_name": self.function_name,
            "module": self.module,
            "signature": self.signature,
            "returns": self.returns,
            "env": ",".join(e.value for e in self.env),
            "source_url": self.source_url,
        }


class DictType(StrEnum):
    INDUSTRY = "industry"
    CONCEPT = "concept"
    INDEX = "index"
    FIELD = "field"
    SUFFIX = "suffix"
    FUND = "fund"


class JqDictChunk(BaseModel):
    id: str
    library: Literal[Library.JQ_DICT] = Library.JQ_DICT
    source: Literal[Source.JQ_OFFICIAL_DOC] = Source.JQ_OFFICIAL_DOC
    code: str
    name: str
    dict_type: DictType
    unit: str | None = None
    sample: str | None = None
    source_description: str = ""
    source_url: str = ""
    parent_code: str | None = None
    content: str
    contextual_content: str
    ingested_at: date = Field(default_factory=date.today)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "library": self.library.value,
            "code": self.code,
            "name": self.name,
            "dict_type": self.dict_type.value,
            "unit": self.unit or "",
            "sample": self.sample or "",
            "source_description": self.source_description,
            "source_url": self.source_url,
        }


class LibraryManifest(BaseModel):
    library: Library
    version: str
    schema_version: str = "1.0"
    chunks_count: int
    embedding_model: str
    rerank_model: str = ""
    ingested_at: date = Field(default_factory=date.today)
    notes: str = ""
