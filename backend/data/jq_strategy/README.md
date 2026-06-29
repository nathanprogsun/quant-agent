# jq_strategy Raw Data

2020-2024 JoinQuant community strategy `.txt` files (620 posts). **Not committed** — load from local disk via `JQ_STRATEGY_DATA_DIR`.

## Setup

```bash
# .env or shell
export JQ_STRATEGY_DATA_DIR="/Users/jung/Desktop/DC42-2022年度精选策略"
```

## Pipeline

```bash
cd backend

# 1. Import txt → raw JSON
uv run python scripts/import_jq_strategy.py --pilot   # 8-sample pilot.json
uv run python scripts/import_jq_strategy.py           # full posts.json (~620)

# 2. LLM 8-dim summaries (optional but recommended for full)
uv run python scripts/summarize_jq_strategy.py --pilot --limit 8
uv run python scripts/summarize_jq_strategy.py        # resumable → raw/summaries.jsonl

# 3. Ingest Chroma + BM25
uv run python scripts/ingest_jq_strategy.py --pilot --reset

# 4. Eval
uv run python scripts/build_eval_jq_strategy.py --mode pilot
uv run python scripts/eval_jq_strategy.py --pilot
```

## Chunk layers

| Layer | Content | Retrieval use |
|-------|---------|---------------|
| summary | 8-dim LLM summary (or title heuristic) | Semantic ("ETF 轮动") |
| entity | API / factor names | Exact ("get_fundamentals") |
| code | Per-function AST slices | Code reuse (`initialize`) |

## PR3 scope (this branch)

- Parser + AST entity extraction (stdlib `ast`)
- Hybrid BM25/vector + BGE rerank
- `search_jq_strategy` tool (`pr_phase=3`)
- Kùzu graph — **deferred** to follow-up
