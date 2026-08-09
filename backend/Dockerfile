# Production Dockerfile for FastAPI Backend
# IMPORTANT: Build context is the backend/ directory (Railway service root = backend/)
# All COPY paths are relative to backend/ — NOT the monorepo root.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies required by sentence-transformers, uvicorn[standard], etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt is at the root of the build context (= backend/)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend source into /app/backend/ so that the absolute import
# "from backend.app.xxx import ..." resolves correctly when uvicorn runs from /app
COPY . /app/backend/

EXPOSE 8000

# Shell form allows ${PORT:-8000} expansion at runtime from Railway's injected $PORT
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
