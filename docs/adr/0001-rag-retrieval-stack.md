# ADR-0001 RAG 检索栈选型

- 状态：已采纳
- 日期：2026-06-24（`docs/jq_kb/PLAN.md` v3.2）
- 关联代码：`backend/app/core/jq_kb/retrievers.py`、`embedding_client.py`、`embeddings.py`、`paths.py`

## 背景

聚宽用户写策略/回测时需检索三类知识：API 文档（jq_api）、数据字典（jq_dict）、社区策略（jq_strategy）。需在 LLM 工具调用延迟内返回高质量片段。

## 决策

采用 hybrid 检索 + cross-encoder 重排两阶段管线，三库共享：

1. **召回**：`QueryFusionRetriever` 生成 N 个查询变体 → `VectorIndexRetriever`(ChromaDB) + `BM25Retriever`(pickle) 并行 → RRF 融合（`mode="reciprocal_rerank"`，按 rank 而非原始分数合并，因 cosine 与 BM25 分数不可比）
2. **重排**：`get_reranker()` 本地 `SentenceTransformerRerank`(BAAI/bge-reranker-large) cross-encoder；本地模型缺失时跳过该步（降级而非报错）

- **Embedding 走远程 HTTP**：`embedding_client.py` 调 OpenAI-compatible `{jq_kb_embedding_base_url}/embeddings`，不本地加载 embedding 模型
- **Reranker 走本地**：`embeddings.py:get_reranker` 从 `backend/data/models/BAAI/bge-reranker-large` 加载；远程备选 `RerankPostprocessor`（HTTP）保留但未在三库装配
- **jq_api 默认 `backtest_env` 过滤**：排除 research-only / live-only API（文档 ♠ 标记），因 agent 生成代码始终在回测环境运行

## 结果

- 正面：检索质量可调（top-k / candidate-multiplier / num_queries），降级路径清晰（无 reranker 仍可用）
- 负面：本地 reranker 需 `hf download` 预置（约 1.3GB）；未预置时静默降级，需日志监控
- Kùzu 图谱为后续计划，未在此栈内
