# Expose service factories for clean imports across the app.
# Always use these factory functions instead of instantiating classes directly
# — they handle singleton caching and config-based switching.

from app.services.llm_client import get_llm_client, LLMClient
from app.services.embedder import get_embedding_service, EmbeddingService
from app.services.vector_store import get_vector_store
from app.services.ingestion import IngestionService
from app.services.retriever import RetrieverService
from app.services.router_agent import RouterAgent
from app.services.critic_agent import CriticAgent
from app.services.orchestrator import Orchestrator

__all__ = [
    "get_llm_client",
    "LLMClient",
    "get_embedding_service",
    "EmbeddingService",
    "get_vector_store",
    "IngestionService",
    "RetrieverService",
    "RouterAgent",
    "CriticAgent",
    "Orchestrator",
]
