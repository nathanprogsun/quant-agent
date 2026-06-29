"""Root test configuration."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from openai import AuthenticationError
from pydantic import SecretStr

from app.settings import get_settings, reload_settings

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Override settings before importing app modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["ENVIRONMENT"] = "local"

# Load backend/.env so skip markers see keys not exported to the shell
load_dotenv(_BACKEND_ROOT / ".env", override=False)


def is_openai_api_key_configured() -> bool:
    """True when OPENAI_API_KEY is set via env or backend/.env (via Settings)."""
    reload_settings()
    key = get_settings().openai_api_key.get_secret_value()
    return bool(key and key.strip())


@pytest.fixture
async def require_working_llm() -> None:
    """Skip live-LLM tests when the configured provider rejects or cannot be reached."""
    if not is_openai_api_key_configured():
        pytest.skip("Requires OPENAI_API_KEY in environment or backend/.env")

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.model,
        api_key=SecretStr(settings.openai_api_key.get_secret_value()),
        base_url=settings.openai_base_url,
        max_retries=0,
        timeout=30,
    )
    try:
        await model.ainvoke([HumanMessage(content="ping")])
    except AuthenticationError as exc:
        pytest.skip(
            "OPENAI_API_KEY is set but rejected by the provider "
            f"({settings.openai_base_url}): {exc}"
        )
    except Exception as exc:
        pytest.skip(f"LLM provider unreachable ({settings.openai_base_url}): {exc}")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
