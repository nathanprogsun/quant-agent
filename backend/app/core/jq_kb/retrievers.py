"""jq_api hybrid retriever — LlamaIndex-native (RRF fusion + BGE rerank).

Architecture (mirrors the official AsyncFusionRAG demo, retrieve-only):

    retrieve()
      ├─ retrieve_by_function_name()     ← metadata exact-match shortcut
      └─ _retrieve_hybrid()
            ├─ _build_fusion_retriever() ← Stage 1-3: query gen + hybrid + RRF
            │     ├─ _build_vector_retriever()
            │     └─ _build_bm25_retriever()
            └─ _build_reranker()           ← Stage 4: BGE cross-encoder rerank

Stage breakdown
---------------
Stage 1  LLM query generation   QueryFusionRetriever generates num_queries variants
Stage 2  Multi-retriever search VectorIndexRetriever (semantic) + BM25Retriever (lexical)
Stage 3  RRF fusion             mode="reciprocal_rerank" — merges ranked lists by rank,
                                NOT by raw score (cosine vs BM25 scores are incomparable)
Stage 4  Cross-encoder rerank   SentenceTransformerRerank (BAAI/bge-reranker-large)

Why BM25Retriever, not KeywordTableSimpleRetriever?
----------------------------------------------------
KeywordTableSimpleRetriever belongs to KeywordTableIndex — a separate index type
that stores an inverted keyword table.  Our pipeline uses VectorStoreIndex
(Chroma) + persisted BM25 nodes; BM25Retriever plugs directly into
QueryFusionRetriever alongside VectorIndexRetriever.  Switching to
KeywordTableSimpleRetriever would require rebuilding a second index and
cannot share the same node store.

Env filter default
------------------
Quant Agent code always runs in the backtest environment.  We default to
``backtest_env`` metadata filter so research-only / live-trading-only APIs
(♠ markers in JQ docs) are excluded from retrieval results.  Pass
``env=JqApiEnvConstraint.ALL`` explicitly to disable the filter (eval/debug).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from llama_index.core import QueryBundle
from llama_index.core.llms.llm import LLM
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core.retrievers import (
    BaseRetriever,
    QueryFusionRetriever,
    VectorIndexRetriever,
)
from llama_index.core.vector_stores import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from llama_index.retrievers.bm25 import BM25Retriever

from app.core.jq_kb.dict_storage import JqDictStore
from app.core.jq_kb.embeddings import get_reranker
from app.core.jq_kb.llm import get_llm
from app.core.jq_kb.schemas import JqApiEnvConstraint
from app.core.jq_kb.storage import JqApiStore
from app.core.jq_kb.strategy_storage import JqStrategyStore

logger = logging.getLogger(__name__)

# Quant Agent always executes in the JQ backtest sandbox.
DEFAULT_ENV: JqApiEnvConstraint = JqApiEnvConstraint.BACKTEST

# Retrieve 2x candidates before reranking trims to top_k.
RERANK_CANDIDATE_MULTIPLIER = 2

# Vector vs BM25 weight in RRF fusion (must sum to 1 when both present).
VECTOR_WEIGHT = 0.6
BM25_WEIGHT = 0.4


@dataclass
class RetrievedChunk:
    """Tool-facing result wrapper (stable contract for tools.py + tests)."""

    chunk_id: str
    score: float
    document: str
    metadata: dict[str, Any]


class JqApiRetriever:
    """Hybrid BM25 + vector retrieval with LLM query-gen + BGE rerank.

    Lifecycle mirrors the demo's ``AsyncFusionRAGPipeline``:
    setup (lazy) → build retrievers → async retrieve → rerank.
    """

    def __init__(
        self,
        store: JqApiStore | None = None,
        *,
        llm: LLM | None = None,
        num_queries: int = 4,
        default_env: JqApiEnvConstraint = DEFAULT_ENV,
    ) -> None:
        self.store = store or JqApiStore()
        self._llm = llm
        self.num_queries = num_queries
        self.default_env = default_env

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        *,
        function_name: str = "",
        env: JqApiEnvConstraint | None = None,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """Retrieve jq_api chunks for a natural-language query.

        Routing:
        - ``function_name`` set → ``retrieve_by_function_name`` (no LLM/RAG)
        - otherwise → ``_retrieve_hybrid`` (full fusion + rerank pipeline)

        ``env`` defaults to ``backtest_env`` (see module docstring).
        """
        if function_name:
            hit = await self.retrieve_by_function_name(function_name)
            if hit:
                logger.info(
                    "jq_api retrieve: function_name shortcut hit=%s query=%r",
                    function_name,
                    query[:80],
                )
                return [hit]
            logger.warning(
                "jq_api retrieve: function_name=%r not found, falling back to hybrid query=%r",
                function_name,
                query[:80],
            )

        effective_env = env if env is not None else self.default_env
        return await self._retrieve_hybrid(
            query,
            env=effective_env,
            top_k=top_k,
        )

    async def retrieve_by_function_name(
        self,
        function_name: str,
    ) -> RetrievedChunk | None:
        """Metadata-filtered exact lookup — bypasses LLM query gen and RAG.

        Uses Chroma metadata filter on ``function_name`` field.
        Equivalent to demo's ``query_with_metadata_filter`` pattern.
        """
        hit = self.store.get_by_function_name(function_name)
        if hit is None:
            return None
        return RetrievedChunk(
            chunk_id=hit["id"],
            score=1.0,
            document=hit["document"],
            metadata=hit["metadata"],
        )

    # ------------------------------------------------------------------
    # Hybrid retrieval pipeline
    # ------------------------------------------------------------------

    async def _retrieve_hybrid(
        self,
        query: str,
        *,
        env: JqApiEnvConstraint,
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Full async pipeline: fusion retrieve → BGE rerank → format."""
        candidate_k = top_k * RERANK_CANDIDATE_MULTIPLIER
        logger.info(
            "jq_api hybrid retrieve: query=%r env=%s top_k=%d candidate_k=%d num_queries=%d",
            query[:80],
            env.value,
            top_k,
            candidate_k,
            self.num_queries,
        )
        fusion = self._build_fusion_retriever(env=env, top_k=candidate_k)
        bundle = QueryBundle(query_str=query)

        # Stage 1-3: LLM query gen + vector/BM25 search + RRF fusion
        nodes = await fusion.aretrieve(bundle)
        fused_count = len(nodes)
        nodes = _filter_nodes_by_env(nodes, env)
        if fused_count != len(nodes):
            logger.debug(
                "jq_api env filter: %d → %d nodes (env=%s)",
                fused_count,
                len(nodes),
                env.value,
            )

        # Stage 4: cross-encoder rerank (BGE)
        reranker = self._build_reranker(top_k=top_k)
        if reranker is not None and nodes:
            try:
                nodes = await reranker.apostprocess_nodes(nodes, query_bundle=bundle)
            except Exception:
                logger.warning(
                    "jq_api rerank failed, using fusion order (top_k=%d)",
                    top_k,
                    exc_info=True,
                )
                nodes = nodes[:top_k]
        else:
            if reranker is None:
                logger.debug("jq_api rerank skipped: reranker unavailable")
            nodes = nodes[:top_k]

        chunks = [_node_to_chunk(n) for n in nodes]
        if chunks:
            logger.info(
                "jq_api hybrid retrieve done: hits=%s",
                _summarize_hits(chunks),
            )
        else:
            logger.warning("jq_api hybrid retrieve: no hits query=%r env=%s", query[:80], env.value)
        return chunks

    # ------------------------------------------------------------------
    # Component builders (demo: build_fusion_retriever / build_reranker)
    # ------------------------------------------------------------------

    def _build_fusion_retriever(
        self,
        *,
        env: JqApiEnvConstraint,
        top_k: int,
    ) -> QueryFusionRetriever:
        """Assemble QueryFusionRetriever: vector + BM25 → RRF."""
        filters = self._build_env_filters(env)
        vector_retriever = self._build_vector_retriever(filters=filters, top_k=top_k)
        bm25_retriever = self._build_bm25_retriever(top_k=top_k)

        retrievers: list[BaseRetriever] = [vector_retriever]
        weights: list[float] | None = None
        if bm25_retriever is not None:
            retrievers.append(bm25_retriever)
            weights = [VECTOR_WEIGHT, BM25_WEIGHT]
        else:
            logger.debug("jq_api fusion: BM25 unavailable, vector-only")

        return QueryFusionRetriever(
            retrievers=retrievers,
            llm=self._get_llm(),
            # RRF: rank-based fusion; safe when retriever score scales differ.
            mode="reciprocal_rerank",
            retriever_weights=weights,
            num_queries=self.num_queries,
            use_async=True,
            similarity_top_k=top_k,
        )

    def _build_vector_retriever(
        self,
        *,
        filters: MetadataFilters | None,
        top_k: int,
    ) -> VectorIndexRetriever:
        """Semantic search over BGE embeddings (Chroma)."""
        return VectorIndexRetriever(
            index=self.store.index,
            similarity_top_k=top_k,
            filters=filters,
        )

    def _build_bm25_retriever(self, *, top_k: int) -> BM25Retriever | None:
        """Lexical search over persisted BM25 index.

        See module docstring for why we use BM25Retriever instead of
        KeywordTableSimpleRetriever.

        Note: ``similarity_top_k`` is set at ingest/load time in ``JqApiStore``.
        We do not override it here — BM25 corpus may be smaller than
        ``top_k`` in pilot/test runs and bm25s raises if k > corpus size.
        """
        _ = top_k  # kept for API symmetry with _build_vector_retriever
        return self.store.load_bm25()

    def _build_reranker(self, *, top_k: int) -> SentenceTransformerRerank | None:
        """Cross-encoder reranker (BAAI/bge-reranker-large)."""
        return get_reranker(top_n=top_k)

    # ------------------------------------------------------------------
    # Metadata filters
    # ------------------------------------------------------------------

    def _build_env_filters(
        self,
        env: JqApiEnvConstraint,
    ) -> MetadataFilters | None:
        """Build Chroma metadata filter for JQ runtime environment.

        Uses boolean ``supports_{env}`` flags (EQ) because ChromaVectorStore
        does not support ``FilterOperator.CONTAINS`` on comma-separated strings.

        Returns None only when ``env=ALL`` (eval / debug — no filtering).
        Default ``backtest_env`` is intentional: Quant Agent code runs
        in the JQ backtest sandbox, not live trading.

        BM25Retriever has no metadata filter — see ``_filter_nodes_by_env``
        applied after fusion as a safety net.
        """
        if env == JqApiEnvConstraint.ALL:
            return None
        return MetadataFilters(
            filters=[
                MetadataFilter(
                    key=f"supports_{env.value}",
                    value="1",
                    operator=FilterOperator.EQ,
                )
            ],
            condition=FilterCondition.AND,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_llm(self) -> LLM:
        if self._llm is None:
            self._llm = get_llm(temperature=0.0)
            model = getattr(self._llm, "model", None) or getattr(self._llm, "model_name", "?")
            logger.debug("jq_api lazy-loaded LLM model=%s", model)
        return self._llm


def _summarize_hits(chunks: list[RetrievedChunk]) -> str:
    return ", ".join(
        f"{c.metadata.get('function_name', c.chunk_id)}:{c.score:.3f}" for c in chunks
    )


def _node_to_chunk(node_with_score: Any) -> RetrievedChunk:
    n = node_with_score
    return RetrievedChunk(
        chunk_id=n.node.node_id,
        score=float(n.score or 0.0),
        document=n.node.text or "",
        metadata=dict(n.node.metadata or {}),
    )


def _node_matches_env(metadata: dict[str, Any], env: JqApiEnvConstraint) -> bool:
    """Post-fusion env filter — covers BM25 path and legacy ingested nodes."""
    if env == JqApiEnvConstraint.ALL:
        return True
    flag_key = f"supports_{env.value}"
    if flag_key in metadata:
        return str(metadata[flag_key]) == "1"
    # Legacy nodes ingested before env_support_flags were added
    env_str = str(metadata.get("env", ""))
    allowed = {e.strip() for e in env_str.split(",") if e.strip()}
    if JqApiEnvConstraint.ALL.value in allowed:
        return True
    return env.value in allowed


def _filter_nodes_by_env(nodes: list[Any], env: JqApiEnvConstraint) -> list[Any]:
    if env == JqApiEnvConstraint.ALL:
        return nodes
    return [n for n in nodes if _node_matches_env(dict(n.node.metadata or {}), env)]


def create_default_jq_api_retriever() -> JqApiRetriever:
    return JqApiRetriever(JqApiStore())


# ---------------------------------------------------------------------------
# jq_dict retriever (PR2) — BM25-heavy fusion, no env filter
# ---------------------------------------------------------------------------

DICT_VECTOR_WEIGHT = 0.3
DICT_BM25_WEIGHT = 0.7


class JqDictRetriever:
    """Hybrid retrieval for jq_dict (industry/concept/index/field/suffix codes)."""

    def __init__(
        self,
        store: Any | None = None,
        *,
        llm: LLM | None = None,
        num_queries: int = 4,
    ) -> None:
        self.store = store or JqDictStore()
        self._llm = llm
        self.num_queries = num_queries

    async def retrieve(
        self,
        query: str,
        *,
        code: str = "",
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        if code:
            hit = await self.retrieve_by_code(code)
            if hit:
                logger.info(
                    "jq_dict retrieve: code shortcut hit=%s query=%r",
                    code,
                    query[:80],
                )
                return [hit]
            logger.warning(
                "jq_dict retrieve: code=%r not found, falling back to hybrid query=%r",
                code,
                query[:80],
            )

        return await self._retrieve_hybrid(query, top_k=top_k)

    async def retrieve_by_code(self, code: str) -> RetrievedChunk | None:
        hit = self.store.get_by_code(code)
        if hit is None:
            return None
        return RetrievedChunk(
            chunk_id=hit["id"],
            score=1.0,
            document=hit["document"],
            metadata=hit["metadata"],
        )

    async def _retrieve_hybrid(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        candidate_k = top_k * RERANK_CANDIDATE_MULTIPLIER
        logger.info(
            "jq_dict hybrid retrieve: query=%r top_k=%d candidate_k=%d num_queries=%d",
            query[:80],
            top_k,
            candidate_k,
            self.num_queries,
        )
        fusion = self._build_fusion_retriever(top_k=candidate_k)
        bundle = QueryBundle(query_str=query)
        nodes = await fusion.aretrieve(bundle)

        reranker = self._build_reranker(top_k=top_k)
        if reranker is not None and nodes:
            try:
                nodes = await reranker.apostprocess_nodes(nodes, query_bundle=bundle)
            except Exception:
                logger.warning(
                    "jq_dict rerank failed, using fusion order (top_k=%d)",
                    top_k,
                    exc_info=True,
                )
                nodes = nodes[:top_k]
        else:
            nodes = nodes[:top_k]

        chunks = [_node_to_chunk(n) for n in nodes]
        if chunks:
            logger.info("jq_dict hybrid retrieve done: hits=%s", _summarize_dict_hits(chunks))
        else:
            logger.warning("jq_dict hybrid retrieve: no hits query=%r", query[:80])
        return chunks

    def _build_fusion_retriever(self, *, top_k: int) -> QueryFusionRetriever:
        vector_retriever = VectorIndexRetriever(
            index=self.store.index,
            similarity_top_k=top_k,
        )
        bm25_retriever = self.store.load_bm25()

        retrievers: list[BaseRetriever] = [vector_retriever]
        weights: list[float] | None = None
        if bm25_retriever is not None:
            retrievers.append(bm25_retriever)
            weights = [DICT_VECTOR_WEIGHT, DICT_BM25_WEIGHT]
        else:
            logger.debug("jq_dict fusion: BM25 unavailable, vector-only")

        return QueryFusionRetriever(
            retrievers=retrievers,
            llm=self._get_llm(),
            mode="reciprocal_rerank",
            retriever_weights=weights,
            num_queries=self.num_queries,
            use_async=True,
            similarity_top_k=top_k,
        )

    def _build_reranker(self, *, top_k: int) -> SentenceTransformerRerank | None:
        return get_reranker(top_n=top_k)

    def _get_llm(self) -> LLM:
        if self._llm is None:
            self._llm = get_llm(temperature=0.0)
        return self._llm


def _summarize_dict_hits(chunks: list[RetrievedChunk]) -> str:
    return ", ".join(
        f"{c.metadata.get('code', c.chunk_id)}:{c.score:.3f}" for c in chunks
    )


def create_default_jq_dict_retriever() -> JqDictRetriever:
    return JqDictRetriever()


# ---------------------------------------------------------------------------
# jq_strategy retriever (PR3) — summary-heavy hybrid retrieval
# ---------------------------------------------------------------------------

STRATEGY_VECTOR_WEIGHT = 0.5
STRATEGY_BM25_WEIGHT = 0.5


class JqStrategyRetriever:
    """Hybrid retrieval for jq_strategy (2020-2024 community strategies)."""

    def __init__(
        self,
        store: Any | None = None,
        *,
        llm: LLM | None = None,
        num_queries: int = 2,
    ) -> None:
        self.store = store or JqStrategyStore()
        self._llm = llm
        self.num_queries = num_queries

    async def retrieve(
        self,
        query: str,
        *,
        post_id: int = 0,
        year: int = 0,
        strategy_type: str = "",
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        if post_id:
            hit = await self.retrieve_by_post_id(post_id)
            if hit:
                logger.info("jq_strategy retrieve: post_id shortcut hit=%s", post_id)
                return [hit]

        return await self._retrieve_hybrid(
            query,
            top_k=top_k,
            year=year,
            strategy_type=strategy_type.strip(),
        )

    async def retrieve_by_post_id(self, post_id: int) -> RetrievedChunk | None:
        hit = self.store.get_by_post_id(post_id, layer="summary")
        if hit is None:
            hit = self.store.get_by_post_id(post_id)
        if hit is None:
            return None
        return RetrievedChunk(
            chunk_id=hit["id"],
            score=1.0,
            document=hit["document"],
            metadata=hit["metadata"],
        )

    async def _retrieve_hybrid(
        self,
        query: str,
        *,
        top_k: int,
        year: int,
        strategy_type: str,
    ) -> list[RetrievedChunk]:
        candidate_k = top_k * RERANK_CANDIDATE_MULTIPLIER
        fusion = self._build_fusion_retriever(
            top_k=candidate_k,
            year=year,
            strategy_type=strategy_type,
        )
        bundle = QueryBundle(query_str=query)
        nodes = await fusion.aretrieve(bundle)

        reranker = self._build_strategy_reranker(top_k=top_k)
        if reranker is not None and nodes:
            try:
                nodes = await reranker.apostprocess_nodes(nodes, query_bundle=bundle)
            except Exception:
                logger.warning("jq_strategy rerank failed, using fusion order", exc_info=True)
                nodes = nodes[:top_k]
        else:
            nodes = nodes[:top_k]

        chunks = [_node_to_chunk(n) for n in nodes]
        if chunks:
            logger.info("jq_strategy hybrid done: %s", _summarize_strategy_hits(chunks))
        return chunks

    def _build_metadata_filters(
        self,
        *,
        year: int,
        strategy_type: str,
    ) -> MetadataFilters | None:
        filters: list[MetadataFilter] = []
        if year:
            filters.append(MetadataFilter(key="year", value=year))
        if strategy_type:
            filters.append(MetadataFilter(key="strategy_type", value=strategy_type))
        if not filters:
            return None
        return MetadataFilters(filters=filters, condition=FilterCondition.AND)

    def _build_fusion_retriever(
        self,
        *,
        top_k: int,
        year: int,
        strategy_type: str,
    ) -> QueryFusionRetriever:
        meta_filters = self._build_metadata_filters(year=year, strategy_type=strategy_type)
        vector_retriever = VectorIndexRetriever(
            index=self.store.index,
            similarity_top_k=top_k,
            filters=meta_filters,
        )
        bm25_retriever = self.store.load_bm25()
        retrievers: list[BaseRetriever] = [vector_retriever]
        weights: list[float] | None = None
        if bm25_retriever is not None:
            retrievers.append(bm25_retriever)
            weights = [STRATEGY_VECTOR_WEIGHT, STRATEGY_BM25_WEIGHT]

        return QueryFusionRetriever(
            retrievers=retrievers,
            llm=self._get_strategy_llm(),
            mode="reciprocal_rerank",
            retriever_weights=weights,
            num_queries=self.num_queries,
            use_async=True,
            similarity_top_k=top_k,
        )

    def _build_strategy_reranker(self, *, top_k: int) -> SentenceTransformerRerank | None:
        return get_reranker(top_n=top_k)

    def _get_strategy_llm(self) -> LLM:
        if self._llm is None:
            self._llm = get_llm(temperature=0.0)
        return self._llm


def _summarize_strategy_hits(chunks: list[RetrievedChunk]) -> str:
    return ", ".join(
        f"{c.metadata.get('title', c.chunk_id)}:{c.score:.3f}" for c in chunks
    )


def create_default_jq_strategy_retriever() -> JqStrategyRetriever:
    return JqStrategyRetriever()
