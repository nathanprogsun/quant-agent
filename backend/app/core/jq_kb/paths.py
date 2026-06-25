"""Default on-disk paths for jq_kb artifacts."""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]

JQ_API_DATA_DIR = BACKEND_ROOT / "data" / "jq_api"
JQ_API_RAW_DIR = JQ_API_DATA_DIR / "raw"
JQ_API_CHROMA_PATH = JQ_API_DATA_DIR / "chroma_db"
JQ_API_BM25_PATH = JQ_API_DATA_DIR / "bm25.pkl"
JQ_API_MANIFEST_PATH = JQ_API_DATA_DIR / "manifest.json"

JQ_API_COLLECTION_NAME = "jq_api_chunks"

JQ_DICT_DATA_DIR = BACKEND_ROOT / "data" / "jq_dict"
JQ_DICT_RAW_DIR = JQ_DICT_DATA_DIR / "raw"
JQ_DICT_CHROMA_PATH = JQ_DICT_DATA_DIR / "chroma_db"
JQ_DICT_BM25_PATH = JQ_DICT_DATA_DIR / "bm25.pkl"
JQ_DICT_MANIFEST_PATH = JQ_DICT_DATA_DIR / "manifest.json"

JQ_DICT_COLLECTION_NAME = "jq_dict_chunks"

JQ_KB_MODELS_DIR = BACKEND_ROOT / "data" / "models"

DEFAULT_EMBEDDING_MODEL_ID = "BAAI/bge-large-zh-v1.5"
DEFAULT_RERANK_MODEL_ID = "BAAI/bge-reranker-large"

JQ_KB_EMBEDDING_MODEL_PATH = JQ_KB_MODELS_DIR / "BAAI" / "bge-large-zh-v1.5"
JQ_KB_RERANK_MODEL_PATH = JQ_KB_MODELS_DIR / "BAAI" / "bge-reranker-large"


def local_model_path(model_id: str) -> Path:
    """Path where ``hf download <model_id> --local-dir`` should place files."""
    return JQ_KB_MODELS_DIR / model_id


def is_local_model_ready(path: Path) -> bool:
    """True if ``hf download --local-dir`` finished (config + weights)."""
    has_config = (path / "config.json").is_file() or (path / "config_sentence_transformers.json").is_file()
    has_weights = any(path.glob("*.safetensors")) or (path / "pytorch_model.bin").is_file()
    return has_config and has_weights

EVAL_DATA_DIR = BACKEND_ROOT / "eval" / "datasets"
EVAL_REPORT_DIR = BACKEND_ROOT / "eval" / "reports"

PILOT_FUNCTIONS = (
    "get_price",
    "order_target",
    "order_value",
    "get_fundamentals",
    "get_index_stocks",
    "history",
    "attribute_history",
    "set_order_cost",
    "get_current_data",
    "get_security_info",
    "get_trade_days",
    "get_industry_stocks",
    "normalize_code",
    "run_daily",
    "initialize",
    "handle_data",
    "order",
    "get_bars",
    "get_extras",
    "log",
)
