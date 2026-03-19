import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.audit import AuditLog, QueryLog, Citation
from app.models.user import Workspace
from app.schemas.query import (
    QueryRequest, QueryResponse, StreamChunk, CitationSchema, CriticReport
)
from app.services.llm_client import LLMClient, get_llm_client
from app.services.retriever import RetrieverService
from app.services.router_agent import RouterAgent, ROUTE_CLARIFY
from app.services.critic_agent import CriticAgent
from app.metrics.prometheus import (
    track_llm_call, LLM_TOKEN_COUNT, ACTIVE_QUERIES
)

settings = get_settings()
logger = get_logger(__name__)


# ── RAG system prompt ─────────────────────────────────────────────────────────
RAG_SYSTEM_PROMPT = """You are a precise research assistant with access to a
curated knowledge base. Answer the user's question using ONLY the provided
source context. Follow these rules:

1. Cite sources using [SOURCE N] notation inline, e.g. "Transformers use
   self-attention [SOURCE 1]."
2. If the context does not contain enough information, say:
   "I could not find sufficient information in the provided sources."
3. Never fabricate facts not present in the sources.
4. Be concise and factual. Avoid filler phrases.
5. Structure longer answers with short paragraphs.
"""


class Orchestrator:
    """
    Stateful agent workflow controller.

    Pipeline (in order):
      Step 1 — Router     : Decide if query is answerable or needs clarification
      Step 2 — Retrieval  : Semantic search → top-K chunks
      Step 3 — Prompt     : Build context-injected prompt with [SOURCE N] labels
      Step 4 — LLM        : Stream tokens to client in real-time
      Step 5 — Critic     : Verify claims against sources, build confidence map
      Step 6 — Persist    : Save QueryLog + Citations + AuditLogs to DB

    Every step is logged to audit_logs so the full decision trail is queryable.
    """

    def __init__(self, db: AsyncSession):
        self._db = db
        self._llm: LLMClient = get_llm_client()
        self._retriever = RetrieverService()
        self._router = RouterAgent(self._llm)
        self._critic = CriticAgent(self._llm)

    async def run_streaming(
        self,
        request: QueryRequest,
        user_id: uuid.UUID,
    ) -> AsyncGenerator[str, None]:
        """
        Main streaming entry point.
        Yields Server-Sent Events (SSE) formatted strings.

        SSE format:
            data: {"type": "token", "data": "Hello"}\n\n
            data: {"type": "citations", "data": [...]}\n\n
            data: {"type": "critic", "data": {...}}\n\n
            data: {"type": "done", "query_log_id": "uuid"}\n\n
        """
        import json

        start_time = time.monotonic()
        ACTIVE_QUERIES.inc()

        # ── Validate workspace ownership ──────────────────────────────────
        workspace = await self._db.get(Workspace, request.workspace_id)
        if not workspace or workspace.owner_id != user_id:
            yield self._sse_event("error", "Workspace not found or access denied.")
            ACTIVE_QUERIES.dec()
            return

        # ── Create QueryLog early (needed for FK in audit logs) ───────────
        query_log = QueryLog(
            id=uuid.uuid4(),
            user_id=user_id,
            workspace_id=request.workspace_id,
            query_text=request.query,
            model_used=self._llm.model_name,
        )
        self._db.add(query_log)
        await self._db.flush()   # get ID without full commit

        try:
            # ── Step 1: Router ────────────────────────────────────────────
            route_result = await self._router.route(
                db=self._db,
                query=request.query,
                query_log_id=query_log.id,
                user_id=user_id,
            )

            if route_result["route"] == ROUTE_CLARIFY:
                suggestion = route_result.get("suggestion", "Please rephrase your query.")
                yield self._sse_event("clarify", suggestion)
                await self._db.commit()
                ACTIVE_QUERIES.dec()
                return

            # ── Step 2: Retrieval ─────────────────────────────────────────
            citations, raw_chunks = await self._retriever.retrieve(
                db=self._db,
                query=request.query,
                workspace_id=request.workspace_id,
                query_log_id=query_log.id,
                top_k=request.top_k,
            )

            if not raw_chunks:
                no_context_msg = (
                    "I could not find relevant information in your documents "
                    "for this query. Please upload relevant documents first."
                )
                yield self._sse_event("token", no_context_msg)
                yield self._sse_event("citations", [])
                yield self._sse_event("done", None, query_log_id=str(query_log.id))
                await self._db.commit()
                ACTIVE_QUERIES.dec()
                return

            # ── Step 3: Build prompt ──────────────────────────────────────
            context_block = self._retriever.build_context_block(raw_chunks)
            prompt = self._build_rag_prompt(request.query, context_block)

            # ── Step 4: Stream LLM tokens ─────────────────────────────────
            full_answer_parts = []
            with track_llm_call(
                provider=self._llm.provider_name,
                model=self._llm.model_name,
            ):
                async for token in self._llm.stream(
                    prompt=prompt,
                    system=RAG_SYSTEM_PROMPT,
                ):
                    full_answer_parts.append(token)
                    yield self._sse_event("token", token)

            full_answer = "".join(full_answer_parts)

            # Approximate token count for metrics (1 token ≈ 4 chars)
            estimated_tokens = len(full_answer) // 4
            LLM_TOKEN_COUNT.labels(
                provider=self._llm.provider_name,
                model=self._llm.model_name,
                direction="completion",
            ).inc(estimated_tokens)

            # ── Send citations to client ──────────────────────────────────
            citations_payload = [c.model_dump(mode="json") for c in citations]
            yield self._sse_event("citations", citations_payload)

            # ── Step 5: Critic verification ───────────────────────────────
            critic_report = await self._critic.verify(
                db=self._db,
                answer=full_answer,
                raw_chunks=raw_chunks,
                query_log_id=query_log.id,
                user_id=user_id,
            )
            yield self._sse_event("critic", critic_report.model_dump(mode="json"))

            # ── Step 6: Persist final state ───────────────────────────────
            latency_ms = int((time.monotonic() - start_time) * 1000)
            query_log.answer_text = full_answer
            query_log.latency_ms = latency_ms
            query_log.critic_score = critic_report.overall_score

            # Persist Citation rows for provenance history
            for citation in citations:
                db_citation = Citation(
                    query_log_id=query_log.id,
                    chunk_id=citation.chunk_id,
                    similarity=citation.similarity,
                    snippet=citation.snippet,
                )
                self._db.add(db_citation)

            # Final LLM call audit entry
            self._db.add(AuditLog(
                query_log_id=query_log.id,
                user_id=user_id,
                event_type="llm_call",
                payload={
                    "model": self._llm.model_name,
                    "provider": self._llm.provider_name,
                    "prompt_chars": len(prompt),
                    "answer_chars": len(full_answer),
                    "latency_ms": latency_ms,
                    "estimated_tokens": estimated_tokens,
                },
            ))

            await self._db.commit()

            # ── Done ──────────────────────────────────────────────────────
            yield self._sse_event("done", None, query_log_id=str(query_log.id))

            logger.info(
                "orchestrator_complete",
                query_log_id=str(query_log.id),
                latency_ms=latency_ms,
                critic_score=critic_report.overall_score,
                chunks_used=len(raw_chunks),
            )

        except Exception as e:
            await self._db.rollback()
            logger.error(
                "orchestrator_error",
                error=str(e),
                query_log_id=str(query_log.id),
            )
            yield self._sse_event("error", f"Pipeline error: {str(e)}")
        finally:
            ACTIVE_QUERIES.dec()

    async def run_sync(
        self,
        request: QueryRequest,
        user_id: uuid.UUID,
    ) -> QueryResponse:
        """
        Non-streaming version — collects all SSE events internally
        and returns a single QueryResponse object.
        Used for testing and non-streaming API clients.
        """
        import json

        tokens = []
        citations = []
        critic = None
        query_log_id = None

        async for event in self.run_streaming(request, user_id):
            # Parse SSE line: "data: {...}\n\n"
            if not event.startswith("data:"):
                continue
            raw = event[5:].strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue

            etype = parsed.get("type")
            if etype == "token":
                tokens.append(parsed.get("data", ""))
            elif etype == "citations":
                citations = parsed.get("data", [])
            elif etype == "critic":
                critic = parsed.get("data")
            elif etype == "done":
                query_log_id = parsed.get("query_log_id")

        return QueryResponse(
            query_log_id=uuid.UUID(query_log_id) if query_log_id else uuid.uuid4(),
            query=request.query,
            answer="".join(tokens),
            model_used=self._llm.model_name,
            latency_ms=0,
            citations=[CitationSchema(**c) for c in citations],
            critic=CriticReport(**critic) if critic else CriticReport(
                overall_score=0.0,
                verified_count=0,
                unverified_count=0,
                partial_count=0,
                claims=[],
            ),
            created_at=datetime.now(timezone.utc),
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_rag_prompt(self, query: str, context_block: str) -> str:
        """
        Builds the full RAG prompt with context injection.
        Context block uses [SOURCE N] labels so the LLM can cite inline.
        """
        return (
            f"CONTEXT FROM KNOWLEDGE BASE:\n"
            f"{context_block}\n\n"
            f"USER QUESTION:\n{query}\n\n"
            f"Answer using only the context above. "
            f"Cite sources inline using [SOURCE N] notation."
        )

    def _sse_event(
        self,
        event_type: str,
        data,
        query_log_id: str = None,
    ) -> str:
        """
        Formats a Server-Sent Event string.
        FastAPI's StreamingResponse yields these directly to the client.

        Format: "data: {json}\n\n"
        The double newline is required by the SSE spec.
        """
        import json

        payload = {"type": event_type, "data": data}
        if query_log_id:
            payload["query_log_id"] = query_log_id

        return f"data: {json.dumps(payload)}\n\n"
