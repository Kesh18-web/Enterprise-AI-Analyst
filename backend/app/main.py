from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.analyze import router as analyze_router
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.documents import router as documents_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.sessions import router as sessions_router
from backend.app.core.config import settings
from backend.app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern FastAPI Lifespan Context Manager handling server startup & graceful shutdown."""
    logger.info(
        f"Started Enterprise AI Analyst FastAPI Server on port {settings.PORT} (env={settings.ENVIRONMENT})"
    )
    yield
    logger.info("Executing graceful shutdown for Enterprise AI Analyst API server.")


app = FastAPI(
    title="Enterprise AI Analyst API",
    description="Production Modular AI Agent Runtime & Hybrid RAG Engine powered by LangGraph, Qdrant, and Firestore",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS — localhost for dev + wildcard regex for Railway deployment domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.up\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API v1 Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(analyze_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
