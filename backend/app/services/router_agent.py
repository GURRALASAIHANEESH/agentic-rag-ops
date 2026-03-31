# backend/app/services/router_agent.py
import json
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.services.llm_client import LLMClient
from app.metrics.prometheus import LLM_REQUEST_COUNT

logger = get_logger(__name__)

# ── Route constants ───────────────────────────────────────────────────────────
ROUTE_LOCAL   = "local"       # answer from vector store
ROUTE_WEB     = "web"         # answer from live web search
ROUTE_CLARIFY = "clarify"     # query is pure gibberish

# ── Router system prompt ──────────────────────────────────────────────────────
ROUTER_SYSTEM_PROMPT = """You are a query router for a RAG system.
Route queries to one of three options:

1. "local" — Use for questions about documents, personal info, resumes, projects,
   technical concepts, research papers, or anything likely in a private knowledge base.
   DEFAULT choice when unsure.

2. "web" — Use ONLY for queries that explicitly need current, real-world, or
   live information: news, today's prices, recent events, live API status,
   "what is happening right now", "latest version of X", "current CEO of Y".
   Use sparingly — only when local documents clearly cannot answer.

3. "clarify" — ONLY for pure gibberish with zero meaning (e.g. "asdf", "???").
   Extremely rare.

Respond with JSON only. No extra text.
{"route": "local", "reason": "Question about documents or known concepts."}
{"route": "web", "reason": "Requires live/current information."}
{"route": "clarify", "reason": "Pure gibberish.", "suggestion": "Try asking: ..."}
"""


class RouterAgent:
    """
    Stateless router that classifies each query as 'local' or 'clarify'
    using a lightweight LLM call with a strict JSON-output prompt.

    Fail-open design: any LLM failure (timeout, malformed JSON) falls back
    to 'local' — better to attempt retrieval than block the user.

    Every decision is written to audit_logs for full traceability.
    """

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    async def route(
        self,
        db: AsyncSession,
        query: str,
        query_log_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        """
        Routes the query. Returns:
        {
            "route":      "local" | "clarify",
            "reason":     str,
            "suggestion": str | None   # only present when route == "clarify"
        }
        """
        logger.info("router_start", query=query[:100], query_log_id=str(query_log_id))

        try:
            raw_response = await self._llm.generate(
                prompt=f'Query: "{query}"\n\nRespond with JSON only.',
                system=ROUTER_SYSTEM_PROMPT,
            )

            # Strip markdown fences if model wraps output in ```json ... ```
            cleaned = raw_response.strip().strip("```json").strip("```").strip()
            decision = json.loads(cleaned)

            route      = decision.get("route", ROUTE_LOCAL)
            reason     = decision.get("reason", "No reason provided.")
            suggestion = decision.get("suggestion")

            # Validate — fail-open to local on unexpected route value
            if route not in (ROUTE_LOCAL, ROUTE_WEB, ROUTE_CLARIFY):
                logger.warning(
                    "router_unexpected_route",
                    route=route,
                    falling_back_to=ROUTE_LOCAL,
                )
                route = ROUTE_LOCAL

        except Exception as e:
            logger.warning("router_failed_fallback", error=str(e))
            route      = ROUTE_LOCAL
            reason     = f"Router failed, defaulting to local retrieval. Error: {e}"
            suggestion = None

        # ── Audit log ─────────────────────────────────────────────────────
        db.add(AuditLog(
            query_log_id=query_log_id,
            user_id=user_id,
            event_type="router_decision",
            payload={
                "query":      query[:200],
                "route":      route,
                "reason":     reason,
                "suggestion": suggestion,
                "model":      self._llm.model_name,
            },
        ))

        LLM_REQUEST_COUNT.labels(
            provider=self._llm.provider_name,
            model=self._llm.model_name,
            status="success",
        ).inc()

        logger.info(
            "router_decision",
            route=route,
            reason=reason[:100],
            query_log_id=str(query_log_id),
        )

        return {"route": route, "reason": reason, "suggestion": suggestion}
