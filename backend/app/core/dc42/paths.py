"""Default on-disk paths for committed DC42 knowledge base artifacts."""

from __future__ import annotations

from pathlib import Path

# backend/app/core/dc42/paths.py -> backend/
BACKEND_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_DC42_DATA_DIR = BACKEND_ROOT / "data" / "dc42"
DEFAULT_DC42_DB_PATH = DEFAULT_DC42_DATA_DIR / "dc42.db"
DEFAULT_CHROMA_PATH = DEFAULT_DC42_DATA_DIR / "chroma_db"
DEFAULT_PARAMETER_LIMITS_PATH = DEFAULT_DC42_DATA_DIR / "parameter_limits.json"
DC42_CHROMA_COLLECTION_NAME = "dc42_chunks"
