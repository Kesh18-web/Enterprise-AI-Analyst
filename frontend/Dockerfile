# Multi-stage Dockerfile for Next.js Frontend (standalone output mode)
# IMPORTANT: Build context is the frontend/ directory (Railway service root = frontend/)
# All COPY paths are relative to frontend/ — NOT the monorepo root.

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

# package.json is at the root of the build context (= frontend/)
COPY package.json package-lock.json* ./
RUN npm ci

# Copy all source files
COPY . ./

# NEXT_PUBLIC_ vars are baked into the JS bundle at BUILD time.
# Railway passes service env vars as Docker build args — declare ARG to receive them.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

# Build Next.js app — output: "standalone" generates .next/standalone/server.js
RUN npm run build

# ── Stage 2: Runner (minimal) ─────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# Copy the self-contained standalone server (includes only needed node_modules subset)
COPY --from=builder /app/.next/standalone ./
# Copy built static assets into the location standalone server expects
COPY --from=builder /app/.next/static ./.next/static
# Copy public directory (images, icons, etc.)
COPY --from=builder /app/public ./public

EXPOSE 3000

# Railway injects $PORT and we pass $HOSTNAME=0.0.0.0 so Next.js binds on all interfaces.
# server.js is placed at /app/server.js by Next.js standalone output.
CMD HOSTNAME=0.0.0.0 PORT=${PORT:-3000} node server.js
