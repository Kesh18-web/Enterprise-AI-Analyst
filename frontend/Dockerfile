# Multi-stage Dockerfile for Next.js Frontend
FROM node:20-alpine AS builder
WORKDIR /app

# Copy package configs and install dependencies
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

# Copy source files
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1

# Build application
RUN npm run build

# Runner stage
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["npm", "run", "start"]
