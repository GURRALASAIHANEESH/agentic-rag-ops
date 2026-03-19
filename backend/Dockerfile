# ─────────────────────────────────────────────────────────────
# Stage 1: Builder
# Installs all Python dependencies into a clean virtual env.
# Kept separate so the final image doesn't include build tools.
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# System deps needed to compile psycopg2, bcrypt, and faiss-cpu
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only requirements first — leverages Docker layer cache.
# If requirements.txt hasn't changed, this layer is reused on rebuild.
COPY requirements.txt .

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ─────────────────────────────────────────────────────────────
# Stage 2: Runtime
# Minimal image — only the venv and app code, no build tools.
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security — never run as root in production
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy virtual env from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=appuser:appgroup . .

# Create upload dir with correct permissions
RUN mkdir -p /app/uploads && chown appuser:appgroup /app/uploads

# Activate the venv for all subsequent commands
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Prevents HuggingFace from writing to /root (non-root user)
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface

RUN mkdir -p /app/.cache/huggingface && \
    chown -R appuser:appgroup /app/.cache

USER appuser

# Expose backend port
EXPOSE 8000

# Health check — Docker will mark container unhealthy if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start with uvicorn.
# --workers 1 for local dev; increase to CPU count for production.
# --timeout-keep-alive 75 keeps SSE connections alive through load balancers.
CMD ["uvicorn", "app.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--workers", "1", \
    "--timeout-keep-alive", "75", \
    "--access-log"]
