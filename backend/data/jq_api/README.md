# jq_api Raw Data

## pilot.json

**Status**: hand-authored seed (NOT scraped from joinquant.com).
**Source structure**: mirrors official JQ API doc schema (function_name, module,
signature, params, returns, examples, env_text).
**Purpose**: validate chunker + retriever + eval pipeline end-to-end without
requiring Chrome MCP login. 20 functions covering common research/backtest/
paper-trading APIs.
**Limitation**: signatures/params may drift from current JQ docs as the platform
evolves. Use only for pipeline smoke-tests, not as ground-truth eval data.

## full.json (future)

To be produced by Chrome MCP crawl of `https://www.joinquant.com/help/api/help`
(requires logged-in browser session). SOP lives in `docs/jq_kb/PLAN.md` §15.

## Files

| File | Purpose |
|---|---|
| `raw/pilot.json` | 20-function seed for pipeline validation |
| `chroma_db/` | ChromaDB persistent store (gitignored, Git LFS in repo) |
| `bm25.pkl` | BM25 index (gitignored) |
| `manifest.json` | ingest metadata: version, chunk count, function_names |

## Regenerate

```bash
# Pilot
.venv/bin/python scripts/ingest_jq_api.py --pilot

# Full (after Chrome MCP crawl produces raw/*.json files)
.venv/bin/python scripts/ingest_jq_api.py
```