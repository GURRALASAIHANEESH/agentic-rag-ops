# RAG Ops — Frontend

Production-grade Next.js frontend for the Agentic RAG system.
Dark-first, accessible, streaming-capable UI built with Tailwind CSS,
Radix UI, and the `eventsource-parser` SSE stack.

---

## Tech stack

| Layer | Choice |
|---|---|
| Framework | Next.js 14 (App Router) |
| Styling | Tailwind CSS (custom design tokens) |
| Components | Radix UI primitives + custom |
| Streaming | `fetch` + `ReadableStream` + `eventsource-parser` |
| State | React Context + `useReducer` |
| Auth | JWT in localStorage + auto-refresh interceptor |
| Testing | Jest + React Testing Library + Playwright |

---

## Quick start

```bash
# 1. Install
npm ci

# 2. Configure
cp .env.example .env.local
# Edit INTERNAL_API_URL to point to your FastAPI backend

# 3. Run dev server
npm run dev
# → http://localhost:3000
```

Ensure the FastAPI backend is running on `http://localhost:8000`
before starting the frontend. All `/api/*` requests are proxied
via `next.config.ts` rewrites — no CORS issues in development.

---

## Project structure

```
src/
├── app/                  # Next.js App Router pages
│   ├── (auth)/           # Login, signup — no shell layout
│   ├── (dashboard)/      # Protected pages — sidebar shell
│   ├── globals.css       # Base styles, design tokens, utilities
│   ├── layout.tsx        # Root layout — fonts, providers
│   └── providers.tsx     # Auth + Workspace + Toast providers
├── components/
│   ├── ui/               # Primitive components (Button, Input, Badge...)
│   ├── QueryConsole.tsx  # Streaming query input + answer display
│   ├── CriticReport.tsx  # Claim verification UI
│   ├── ProvenanceViewer.tsx # Source list + detail modal
│   ├── DocumentUploader.tsx # Drag-and-drop file ingestion
│   └── WorkspacePanel.tsx   # Workspace switcher + create modal
├── contexts/             # Auth and Workspace React contexts
├── hooks/                # useStreaming, useWorkspace, useDocumentStatus
├── lib/                  # api.ts, auth.ts, streaming.ts
└── types/                # All shared TypeScript interfaces
```

---

## Streaming architecture

The `QueryConsole` component streams responses from the backend
using a custom `fetch`-based SSE client (`src/lib/streaming.ts`).

```
Browser                    Next.js proxy         FastAPI
  │                              │                   │
  │── POST /api/query ──────────>│                   │
  │                              │── POST /api/query >│
  │                              │<── SSE stream ────│
  │<── SSE stream ───────────────│                   │
  │                              │                   │
token events → APPEND_TOKEN reducer → textarea renders
citations  → SET_CITATIONS → ProvenanceViewer updates
critic     → SET_CRITIC    → CriticReport renders
done       → DONE          → latency/cost bar updates
```

Why `fetch` instead of `EventSource`:
- `EventSource` only supports GET requests with no custom headers
- `fetch` + `ReadableStream` supports POST + Authorization header
- `eventsource-parser` handles the SSE framing on the raw stream

---

## Auth flow

```
1. Login  → POST /api/auth/login → store access + refresh tokens
2. Every request → axios interceptor attaches Bearer token
3. On 401 → interceptor calls /api/auth/refresh automatically
4. On refresh failure → clear localStorage → redirect /login
5. On mount → refreshIfNeeded() checks token expiry proactively
```

Tokens are stored in `localStorage`. The middleware uses a
`ragops_session` cookie (set client-side on login) as a presence
signal for server-side route protection. The actual token is
never in a cookie — only in `localStorage`.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `INTERNAL_API_URL` | Yes | Backend URL for server-side Next.js calls |
| `NEXT_PUBLIC_API_URL` | Yes | Backend URL for browser fallback |
| `NEXT_PUBLIC_APP_NAME` | No | App name shown in UI |
| `NEXT_PUBLIC_DEFAULT_PROVIDER` | No | Default LLM provider in QueryConsole |

---

## Docker

```bash
# Build
docker build \
  --build-arg NEXT_PUBLIC_API_URL=https://your-api.com \
  -t ragops-frontend .

# Run
docker run -p 3000:3000 \
  -e INTERNAL_API_URL=http://api:8000 \
  ragops-frontend
```

The Dockerfile uses a 3-stage build:
- `deps` — install node_modules (cached layer)
- `builder` — compile Next.js with `output: standalone`
- `runner` — minimal Alpine image, non-root user, ~120MB total

---

## Security notes

### File upload
- MIME type validated client-side before upload (`ACCEPTED_TYPES` map)
- Filename is never interpolated into HTML — React escapes it
- Max file size enforced client-side (25MB) and should also be
  enforced server-side in FastAPI (`UploadFile` size check)
- **Virus scan hook**: `DocumentUploader` has a placeholder comment
  for a virus-scan integration. In production, pipe uploaded files
  through ClamAV or a cloud AV API before ingesting into the vector
  store. The current implementation skips this step.

### XSS
- All user content rendered via React — no `dangerouslySetInnerHTML`
- The `HighlightedText` component splits on regex and renders
  `<mark>` elements — no raw HTML injection

### CSP
The `Content-Security-Policy` header in `next.config.ts` is
intentionally permissive in development (`unsafe-eval` for HMR).
Tighten before production:
- Remove `unsafe-eval`
- Replace `unsafe-inline` scripts with a nonce
- Add your CDN domain to `connect-src`

### Token storage
`localStorage` is accessible to any JS on the page. If your threat
model requires stronger isolation, migrate tokens to `httpOnly`
cookies and update the auth interceptor accordingly.

---

## Running tests

```bash
# Type check
npm run type-check

# Lint
npm run lint

# Unit tests (Jest)
npm test

# E2E tests (Playwright)
npx playwright install --with-deps
npm run test:e2e
```

Playwright specs live in `tests/` (already scaffolded).
The `query_flow.spec.ts` test covers:
1. Signup → create workspace → upload doc → run query
2. Streaming answer appears token by token
3. Clicking a citation opens the source modal
4. Provenance viewer shows correct source metadata

---

## Branch strategy

| Branch | Purpose |
|---|---|
| `feat/ui-wireframe` | Static pages + CSS tokens |
| `feat/query-stream` | QueryConsole + streaming mock |
| `feat/provenance` | ProvenanceViewer + DocumentUploader |
| `ui-polish` | Accessibility fixes + Playwright passing |

Do not merge to `main` until Playwright E2E for query flow passes.
