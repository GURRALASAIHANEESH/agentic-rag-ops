from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import get_settings
from app.core.database import ensure_pgvector_extension, check_db_health
from app.core.logging import configure_logging, get_logger


# Import all routers
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.query import router as query_router
from app.api.retrieval import router as retrieval_router

settings = get_settings()
logger = get_logger(__name__)


# ── Rate limiter (slowapi wraps Redis or in-memory) ───────────────────────────
# Using in-memory store for local dev — swap to Redis backend in production:
# Limiter(key_func=get_remote_address, storage_uri="redis://localhost:6379")
limiter = Limiter(key_func=get_remote_address)


# ── App lifespan (replaces deprecated @app.on_event) ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    configure_logging()
    logger.info("starting_up", app=settings.APP_NAME, env=settings.ENVIRONMENT)

    # Ensure pgvector extension exists
    await ensure_pgvector_extension()
    logger.info("database_ready")

    # Ensure upload directory exists
    import os
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    logger.info("upload_dir_ready", path=settings.UPLOAD_DIR)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("shutting_down", app=settings.APP_NAME)


# ── FastAPI app factory ───────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Agentic RAG platform with retrieval, critic, and provenance.",
        docs_url="/docs" if settings.DEBUG else None,   # hide Swagger in production
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ── Rate limiter state ────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS ──────────────────────────────────────────────────────────────
    # Tighten allowed_origins in production to your actual frontend domain
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"] if settings.DEBUG else ["https://yourdomain.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Prometheus metrics ────────────────────────────────────────────────
    if settings.PROMETHEUS_ENABLED:
        Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    # ── Routers ───────────────────────────────────────────────────────────
    app.include_router(auth_router,       prefix="/api/auth",      tags=["Auth"])
    app.include_router(documents_router,  prefix="/api/documents",  tags=["Documents"])
    app.include_router(query_router,      prefix="/api/query",      tags=["Query"])
    app.include_router(retrieval_router,  prefix="/api/retrieval",  tags=["Retrieval"])

    # ── Global exception handlers ─────────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # Return clean validation errors — never expose internal stack traces.
        # Pydantic v2 `exc.errors()` may include non-serializable objects (e.g.
        # ValueError in 'ctx') — convert them to strings to make it JSON-safe.
        def _safe_errors(errors):
            safe = []
            for e in errors:
                err = dict(e)
                if "ctx" in err:
                    err["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
                safe.append(err)
            return safe

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": _safe_errors(exc.errors()), "body": str(exc.body)},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )

    # ── Health endpoints ──────────────────────────────────────────────────
    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health():
        db_ok = await check_db_health()
        return {
            "status": "ok" if db_ok else "degraded",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "database": "ok" if db_ok else "unreachable",
        }

    @app.get("/", include_in_schema=False)
    async def root():
        return {"message": f"{settings.APP_NAME} is running."}

    return app


# ── Entry point ───────────────────────────────────────────────────────────────
app = create_app()
