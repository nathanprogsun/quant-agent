"""Root test configuration."""
from __future__ import annotations

import os

import pytest

# Override settings before importing app modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["ENVIRONMENT"] = "local"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
