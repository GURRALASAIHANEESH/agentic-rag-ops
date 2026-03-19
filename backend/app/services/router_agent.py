import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.services.llm_client import LLMClient
from app.metrics.prometheus import LLM_REQUEST_COUNT

settings = get_settings()
logger = get_logger(__name__)

# Ã¢â€â‚¬Ã¢â€â‚¬ Route decisions Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
ROUTE_LOCAL = "local"       # answer from vector store only
ROUTE_CLARIFY = "clarify"   # query is too vague, ask user to rephrase


# Ã¢â€â‚¬Ã¢â€â‚¬ Router system prompt Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
ROUTER_SYSTEM_PROMPT = ROUTER_SYSTEM_PROMPT = """You are a query router for a RAG system.
Route queries to one of two options:

1. "local" - Use for ALL real questions. Any question about a person, skills, resume,
   technology, project, or concept routes here. Short questions like "what is X",
   "what are my skills", "summarize my resume", "tell me about Y" are ALWAYS "local".

2. "clarify" - ONLY for pure gibberish with zero meaning (e.g. "asdf", "???").
   Extremely rare. Default to "local" when in doubt.

Respond with JSON only. No extra text.
{"route": "local", "reason": "Query is answerable from documents."}
{"route": "clarify", "reason": "Pure gibberish.", "suggestion": "Try asking: ..."}
"""


class RouterAgent:
    """
    Stateful router that decides whether a query can be answered
    from the local vector store or needs clarification.

    Decision logic:
      - Uses a lightweight LLM call with a strict JSON-output prompt
      - Falls back to 'local' if the LLM response is malformed
        (fail-open: better to attempt retrieval than block the user)

    Every decision is logged to audit_logs for traceability.
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
        Routes the query. Returns a dict:
          {
            "route": "local" | "clarify",
            "reason": str,
            "suggestion": str | None   # only present if route == "clarify"
          }
        """
        import json

        logger.info("router_start", query=query[:100], query_log_id=str(query_log_id))

        try:
            raw_response = await self._llm.generate(
                prompt=f'Query: "{query}"\n\nRespond with JSON only.',
                system=ROUTER_SYSTEM_PROMPT,
            )

            # Parse LLM JSON response
            # Strip markdown code fences if model wraps in ```json ... ```
            cleaned = raw_response.strip().strip("```json").strip("```").strip()
            decision = json.loads(cleaned)

            route = decision.get("route", ROUTE_LOCAL)
            reason = decision.get("reason", "No reason provided.")
            suggestion = decision.get("suggestion")

            # Validate route value Ã¢â‚¬â€ fail-open to local on unexpected values
            if route not in (ROUTE_LOCAL, ROUTE_CLARIFY):
                logger.warning(
                    "router_unexpected_route",
                    route=route,
                    falling_back_to=ROUTE_LOCAL,
                )
                route = ROUTE_LOCAL

        except Exception as e:
            # Any failure (JSON parse error, LLM timeout) Ã¢â€ â€™ fail-open to local
            logger.warning("router_failed_fallback", error=str(e))
            route = ROUTE_LOCAL
            reason = f"Router failed, defaulting to local retrieval. Error: {str(e)}"
            suggestion = None

        # Ã¢â€â‚¬Ã¢â€â‚¬ Audit log Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        audit = AuditLog(
            query_log_id=query_log_id,
            user_id=user_id,
            event_type="router_decision",
            payload={
                "query": query[:200],
                "route": route,
                "reason": reason,
                "suggestion": suggestion,
                "model": self._llm.model_name,
            },
        )
        db.add(audit)

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

        return {
            "route": route,
            "reason": reason,
            "suggestion": suggestion,
        }
