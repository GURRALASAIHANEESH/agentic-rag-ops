# ─────────────────────────────────────────────────────────────
# Multi-stage Dockerfile for the Next.js frontend.
# Stage 1: deps    — install production node_modules
# Stage 2: builder — compile Next.js with standalone output
# Stage 3: runner  — minimal production image (~120MB)
# ─────────────────────────────────────────────────────────────

# ── Stage 1: Install dependencies ────────────────────────────
FROM node:20-alpine AS deps

RUN apk add --no-cache libc6-compat

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci --frozen-lockfile

# ── Stage 2: Build ────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules

COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_APP_NAME="RAG Ops"
ARG NEXT_PUBLIC_APP_VERSION="1.0.0"
ARG INTERNAL_API_URL=http://localhost:8000

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_APP_NAME=$NEXT_PUBLIC_APP_NAME
ENV NEXT_PUBLIC_APP_VERSION=$NEXT_PUBLIC_APP_VERSION
ENV INTERNAL_API_URL=$INTERNAL_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ── Stage 3: Production runner ────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
    && adduser  --system --uid 1001 nextjs

COPY --from=builder /app/public                    ./public
COPY --from=builder /app/.next/standalone          ./
COPY --from=builder /app/.next/static ./.next/static

RUN chown -R nextjs:nodejs /app

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:3000/api/health 2>/dev/null || exit 1

CMD ["node", "server.js"]