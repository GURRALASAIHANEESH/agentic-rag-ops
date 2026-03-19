import logging
import sys
from typing import Any

import structlog
from app.core.config import get_settings

settings = get_settings()


def configure_logging() -> None:
    """
    Sets up structured logging using structlog.
    - In production (LOG_FORMAT=json): outputs newline-delimited JSON — easy to
      ship to Loki, CloudWatch, or Datadog.
    - In development (LOG_FORMAT=text): outputs colourised, human-readable logs.

    Call this once at app startup in main.py lifespan.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Shared processors applied to every log event
    shared_processors = [
        structlog.contextvars.merge_contextvars,        # attach request-scoped fields
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.LOG_FORMAT == "json":
        # Production: machine-readable JSON
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: colourised console output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Silence noisy third-party loggers in production
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.DEBUG else logging.WARNING
    )


def get_logger(name: str) -> Any:
    """
    Returns a structlog logger bound to a given name.

    Usage:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("ingestion_complete", doc_id=str(doc.id), chunks=42)
    """
    return structlog.get_logger(name)
