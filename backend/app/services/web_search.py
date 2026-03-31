# backend/app/services/web_search.py
"""
Async DuckDuckGo web search via the duckduckgo-search library.

duckduckgo-search handles DDG's bot-detection, token negotiation, and
API endpoint rotation internally — far more reliable than raw HTTP scraping.
Zero API key required. Free tier is sufficient for RAG fallback usage.

Result shape duck-types RetrieverService's ChunkResult so orchestrator.py
passes web results through build_context_block() and
_build_citations_from_chunks() without any modification.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_RESULTS = 5
_SEARCH_TIMEOUT = 10.0  # seconds — hard ceiling for web search


@dataclass
class WebResult:
    """
    Duck-types RetrieverService's ChunkResult.

    ChunkResult fields used by orchestrator:
        .chunk_id       → uuid.UUID
        .document_id    → uuid.UUID
        .chunk_index    → int  (rank)
        .content        → str  (shown in context block + citations)
        .similarity     → float (shown as confidence score)
        .metadata       → dict with keys: filename, section, doc_namespace,
                          source_type, page_num
    """
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    similarity: float
    metadata: dict = field(default_factory=dict)


class WebSearchService:
    """
    Wraps duckduckgo-search in an async interface.

    duckduckgo_search.DDGS.text() is synchronous — we run it in a thread
    pool via asyncio.to_thread() to stay fully async and never block the
    event loop. Same pattern used by the reranker in retriever.py.

    Fail-open: any exception returns [] — caller decides fallback.
    """

    async def search(
        self,
        query: str,
        max_results: int = _MAX_RESULTS,
    ) -> list[WebResult]:
        """
        Searches DuckDuckGo and returns up to max_results WebResult objects.
        Returns [] on any error — never raises.
        """
        logger.info("web_search.start", query=query[:100])

        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(self._sync_search, query, max_results),
                timeout=_SEARCH_TIMEOUT,
            )
            logger.info(
                "web_search.complete",
                query=query[:100],
                results_found=len(results),
            )
            return results

        except asyncio.TimeoutError:
            logger.warning("web_search.timeout", query=query[:100])
            return []

        except Exception as exc:
            logger.error("web_search.error", error=str(exc), query=query[:100])
            return []

    def _sync_search(
        self,
        query: str,
        max_results: int,
    ) -> list[WebResult]:
        """
        Synchronous DDG search — runs inside asyncio.to_thread().
        Isolated here so the async interface stays clean.
        """
        from ddgs import DDGS

        results: list[WebResult] = []

        with DDGS() as ddgs:
            for rank, hit in enumerate(
                ddgs.text(query, max_results=max_results)
            ):
                if rank >= max_results:
                    break

                title   = hit.get("title", "").strip()
                body    = hit.get("body", "").strip()
                url     = hit.get("href", "").strip()

                # Combine title + body for richer context in the LLM prompt
                content = f"{title}: {body}" if body else title
                if not content:
                    continue

                # Rank 0 = most relevant → 1.0, rank 4 → 0.68
                # Compressed range signals web source vs vector match
                # without making them look artificially high confidence
                similarity = round(1.0 - (rank * 0.08), 2)

                results.append(WebResult(
                    chunk_id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    chunk_index=rank,
                    content=content,
                    similarity=similarity,
                    metadata={
                        "filename": url,
                        "section": "Web",
                        "doc_namespace": "web",
                        "source_type": "web_search",
                        "page_num": 0,
                    },
                ))

        logger.debug(
            "web_search.parsed",
            results_count=len(results),
            query=query[:80],
        )
        return results
