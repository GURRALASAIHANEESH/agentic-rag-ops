# 🧠 RAG Ops — Agentic Intelligence Platform

> A production-grade Retrieval-Augmented Generation (RAG) system with multi-agent 
> orchestration, real-time streaming, critic verification, and a full-stack 
> observability dashboard.

![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-336791?logo=postgresql)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🤖 **Agentic Orchestration** | Router agent classifies queries and dispatches to local RAG, web search, or hybrid pipelines |
| ⚡ **Streaming Answers** | Token-by-token SSE streaming with live latency tracking |
| 🔍 **Critic Verification** | Independent agent verifies each claim with source grounding and confidence scoring |
| 📎 **Provenance Panel** | Real-time source evidence viewer with similarity scores, snippet highlighting, and audit trail |
| 🗂️ **Multi-Workspace** | Isolated document collections per workspace with role-based access control |
| 📄 **Document Ingestion** | PDF and TXT upload with async chunking, embedding, and pgvector indexing |
| 🌐 **Web Search Fallback** | Live web retrieval when local knowledge is insufficient |
| 🧩 **Multi-LLM Support** | Switch between Local Llama, Groq, and OpenAI per query |
| 📊 **Observability** | Prometheus metrics, Grafana dashboards, and structured audit logging |
| 🔐 **Auth & Rate Limiting** | JWT-based authentication with per-workspace rate limiting |

---

## 🏗️ Architecture

```text
User Query
│
▼
┌──────────────────────────────────────────┐
│           Next.js Frontend               │
│  QueryConsole · ProvenanceViewer         │
│  CriticReport · WorkspacePanel           │
└───────────────────┬──────────────────────┘
                    │  SSE Stream
                    ▼
┌──────────────────────────────────────────┐
│             FastAPI Backend              │
│                                          │
│   ┌─────────────┐                        │
│   │ Router Agent│──► local / web /       │
│   └─────────────┘    hybrid              │
│          │                               │
│          ▼                               │
│   ┌──────────────────┐                   │
│   │   Orchestrator   │                   │
│   │  (RAG Pipeline)  │                   │
│   └────────┬─────────┘                   │
│            │                             │
│       ┌────┴────┐                        │
│       │         │                        │
│       ▼         ▼                        │
│   pgvector   Web Search                  │
│             (SerpAPI)                    │
│       │                                  │
│       ▼                                  │
│   ┌──────────────┐                       │
│   │  Critic Agent│                       │
│   └──────────────┘                       │
└──────────────────────────────────────────┘
                    │
                    ▼
         PostgreSQL + Redis
                    │
                    ▼
      Prometheus + Grafana
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, Radix UI |
| **Backend** | FastAPI, Python 3.11, SSE Streaming |
| **Vector DB** | PostgreSQL + pgvector |
| **Embeddings** | Sentence Transformers (local) |
| **LLM** | Ollama (Llama 3), Groq API, OpenAI API |
| **Cache** | Redis |
| **Ingestion** | LangChain Text Splitters, Async Workers |
| **Observability** | FastAPI Docs, Structured Logging |
| **Infrastructure** | Docker Compose |
| **CI/CD** | GitHub Actions |
| **Testing** | Pytest |

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose installed
- 8 GB+ RAM *(required for local LLM inference)*

---

### 1. Clone the Repository

```bash
git clone https://github.com/GURRALASAIHANEESH/agentic-rag-ops.git
cd agentic-rag-ops
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env — set GROQ_API_KEY or OPENAI_API_KEY if not using a local LLM
```

### 3. Start All Services

```bash
docker compose up --build
```

### 4. Create your account
http://localhost:3000/register

> Register a new account, then create a workspace to start uploading documents and querying.

---

## 📁 Project Structure

```text
RAG_Ops/
├── .github/
│   └── workflows/
│       └── ci.yml                     # GitHub Actions CI pipeline
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py                # Auth endpoints
│   │   │   ├── documents.py           # Document management API
│   │   │   ├── query.py               # Query & SSE streaming API
│   │   │   └── retrieval.py           # Retrieval endpoints
│   │   ├── core/
│   │   │   ├── config.py              # App configuration
│   │   │   ├── database.py            # DB connection & session
│   │   │   ├── dependencies.py        # FastAPI dependency injection
│   │   │   ├── logging.py             # Structured logging setup
│   │   │   └── security.py            # JWT & auth utilities
│   │   ├── metrics/
│   │   │   └── prometheus.py          # Prometheus metrics export
│   │   ├── models/
│   │   │   ├── audit.py               # Audit log model
│   │   │   ├── document.py            # Document & chunk models
│   │   │   ├── eval.py                # Evaluation results model
│   │   │   └── user.py                # User & workspace models
│   │   ├── schemas/
│   │   │   ├── auth.py                # Auth request/response schemas
│   │   │   ├── document.py            # Document schemas
│   │   │   └── query.py               # Query schemas
│   │   ├── services/
│   │   │   ├── critic_agent.py        # Claim verification agent
│   │   │   ├── embedder.py            # Embedding generation
│   │   │   ├── evaluator.py           # Answer evaluation service
│   │   │   ├── ingestion.py           # Document chunking & indexing
│   │   │   ├── llm_client.py          # Multi-LLM client (Ollama/Groq/OpenAI)
│   │   │   ├── orchestrator.py        # RAG pipeline orchestrator
│   │   │   ├── rate_limiter.py        # Per-workspace rate limiting
│   │   │   ├── retriever.py           # Vector similarity retrieval
│   │   │   ├── router_agent.py        # Query classification & routing
│   │   │   ├── vector_store.py        # pgvector store interface
│   │   │   └── web_search.py          # Live web retrieval (SerpAPI)
│   │   ├── workers/
│   │   │   └── ingestion_worker.py    # Async background ingestion worker
│   │   └── main.py                    # FastAPI app entrypoint
│   ├── migrations/                    # Alembic DB migrations
│   ├── sample_docs/                   # Sample documents for testing
│   ├── scripts/
│   │   ├── compute_metrics.py         # Offline metrics computation
│   │   ├── ingest_sample_docs.py      # Bulk sample doc ingestion
│   │   ├── requeue_pending.py         # Requeue failed ingestion jobs
│   │   └── seed_db.py                 # Database seeding script
│   ├── tests/
│   │   ├── conftest.py                # Pytest fixtures
│   │   ├── test_auth.py               # Auth tests
│   │   ├── test_critic.py             # Critic agent tests
│   │   ├── test_ingestion.py          # Ingestion pipeline tests
│   │   ├── test_orchestrator.py       # Orchestrator tests
│   │   └── test_retrieval.py          # Retrieval tests
│   ├── Dockerfile
│   ├── alembic.ini
│   └── requirements.txt
│
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── (auth)/
│   │   │   │   ├── login/page.tsx     # Login page
│   │   │   │   └── signup/page.tsx    # Signup page
│   │   │   ├── (dashboard)/
│   │   │   │   ├── query/page.tsx     # Query interface page
│   │   │   │   ├── upload/page.tsx    # Document upload page
│   │   │   │   ├── workspace/page.tsx # Workspace management page
│   │   │   │   ├── layout.tsx         # Dashboard layout
│   │   │   │   └── page.tsx           # Dashboard home
│   │   │   ├── api/query/route.ts     # Next.js API route proxy
│   │   │   ├── globals.css
│   │   │   ├── layout.tsx             # Root layout
│   │   │   └── providers.tsx          # Global context providers
│   │   ├── components/
│   │   │   ├── ui/                    # Reusable UI primitives
│   │   │   │   ├── Badge.tsx
│   │   │   │   ├── Button.tsx
│   │   │   │   ├── Card.tsx
│   │   │   │   ├── Input.tsx
│   │   │   │   ├── Skeleton.tsx
│   │   │   │   └── Toast.tsx
│   │   │   ├── CriticReport.tsx       # Critic verification display
│   │   │   ├── DocumentUploader.tsx   # File upload component
│   │   │   ├── ProvenanceViewer.tsx   # Source evidence panel
│   │   │   ├── QueryConsole.tsx       # Main query interface
│   │   │   └── WorkspacePanel.tsx     # Workspace selector/manager
│   │   ├── contexts/
│   │   │   ├── AuthContext.tsx        # Auth state context
│   │   │   └── WorkspaceContext.tsx   # Active workspace context
│   │   ├── hooks/
│   │   │   ├── useStreaming.ts        # SSE streaming hook
│   │   │   └── useWorkspace.ts        # Workspace management hook
│   │   ├── lib/
│   │   │   ├── api.ts                 # API client
│   │   │   ├── auth.ts                # Auth helpers
│   │   │   └── streaming.ts           # SSE stream utilities
│   │   ├── types/
│   │   │   └── index.ts               # Shared TypeScript types
│   │   └── middleware.ts              # Next.js route middleware
│   ├── Dockerfile
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── package.json
│
│
├── llm/
│   ├── setup_llama.sh                 # Ollama + Llama 3 setup script
│   ├── run_server.sh                  # LLM server startup script
│   └── README.md                      # Local LLM setup guide
│
├── .env.example                       # Environment variable template
├── docker-compose.yml                 # Development stack
├── docker-compose.prod.yml            # Production stack
├── openapi.yaml                       # OpenAPI spec
├── Makefile                           # Dev workflow shortcuts
└── README.md
```

---

## 🔑 Environment Variables

| Variable | Description | Required |
|---|---|:---:|
| `DATABASE_URL` | PostgreSQL connection string | ✅ |
| `REDIS_URL` | Redis connection string | ✅ |
| `JWT_SECRET` | Auth token secret | ✅ |
| `GROQ_API_KEY` | Groq LLM API key | ⬜ Optional |
| `OPENAI_API_KEY` | OpenAI API key | ⬜ Optional |
| `SERPAPI_KEY` | Web search API key | ⬜ Optional |

> See `.env.example` for a full list of all configurable variables.

---

## 🧪 Testing

### Backend Unit Tests

```bash
cd backend
pytest tests/ -v
```

### Ingest Sample Documents

```bash
docker compose exec backend python scripts/ingest_sample_docs.py
```

---

## 📊 Observability

| Tool | URL | Purpose |
|---|---|---|

| **FastAPI Docs** | http://localhost:8000/docs | Interactive API explorer |



---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!
Feel free to open a [GitHub Issue](https://github.com/GURRALASAIHANEESH/agentic-rag-ops/issues) or submit a pull request.

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.