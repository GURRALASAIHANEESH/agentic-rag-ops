.PHONY: dev test ingest seed migrate lint build

# ─── Composite ────────────────────────────────────────────────────────────────
dev:
	docker compose up -d
	@echo "Starting backend…"
	cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
	@echo "Starting frontend…"
	cd frontend && npm run dev

# ─── Testing ──────────────────────────────────────────────────────────────────
test: test-backend test-frontend

test-backend:
	cd backend && .venv/Scripts/activate && pytest tests/ -q

test-frontend:
	cd frontend && npm run typecheck

test-e2e:
	cd e2e && npx playwright test

# ─── Data ─────────────────────────────────────────────────────────────────────
seed:
	cd backend && .venv/Scripts/python scripts/seed_db.py

ingest:
	cd backend && .venv/Scripts/python scripts/ingest_sample_docs.py

# ─── DB ───────────────────────────────────────────────────────────────────────
migrate:
	cd backend && .venv/Scripts/python -m alembic upgrade head

# ─── Build ────────────────────────────────────────────────────────────────────
build:
	cd frontend && npm run build
	docker build -t ragops-backend ./backend

# ─── Lint ─────────────────────────────────────────────────────────────────────
lint:
	cd backend && .venv/Scripts/ruff check app/ tests/
	cd frontend && npm run lint
