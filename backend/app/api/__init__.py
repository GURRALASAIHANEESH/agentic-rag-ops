# Expose all routers for clean imports in main.py
# Each router is mounted with its prefix in app/main.py

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.query import router as query_router
from app.api.retrieval import router as retrieval_router

__all__ = [
    "auth_router",
    "documents_router",
    "query_router",
    "retrieval_router",
]
