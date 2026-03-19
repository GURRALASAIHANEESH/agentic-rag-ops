# Import all models here so Alembic's autogenerate can discover them
# and SQLAlchemy's metadata is fully populated before migrations run.
# Order matters: User → Workspace → Document → Chunk → QueryLog → Citation → AuditLog

from app.models.user import User, Workspace
from app.models.document import Document, Chunk
from app.models.audit import QueryLog, Citation, AuditLog

__all__ = [
    "User",
    "Workspace",
    "Document",
    "Chunk",
    "QueryLog",
    "Citation",
    "AuditLog",
]
