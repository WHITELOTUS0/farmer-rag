"""
FastAPI application entrypoint for the Farmer RAG backend.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import get_settings
from src.api.routes.health import router as health_router
from src.api.routes.chat import router as chat_router
from src.api.routes.auth import router as auth_router
from src.api.routes.admin import router as admin_router
from src.api.routes.users import router as users_router
from src.api.routes.farmers import router as farmers_router
from src.api.routes.conversations import router as conversations_router
from src.api.routes.documents import router as documents_router
from src.api.routes.search import router as search_router
from src.api.routes.farms import router as farms_router
from src.api.routes.crops import router as crops_router
from src.api.routes.metrics import router as metrics_router
from src.api.workers.job_worker import worker_loop


def create_app() -> FastAPI:
    settings = get_settings()

    if settings.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.langchain_tracing_v2 else "false"
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.job_worker = asyncio.create_task(
            worker_loop(settings.job_poll_interval_seconds)
        )
        yield
        worker = getattr(app.state, "job_worker", None)
        if worker:
            worker.cancel()

    app = FastAPI(
        title="Farmer RAG Backend",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS (frontend will be in a separate app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger = logging.getLogger("farmer_rag.requests")

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info("%s %s -> %s (%sms)", request.method, request.url.path, response.status_code, duration_ms)
        return response

    rate_limit = settings.rate_limit_requests
    window = settings.rate_limit_window_seconds
    rate_state = defaultdict(lambda: deque())

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if rate_limit <= 0 or request.url.path == "/metrics":
            return await call_next(request)

        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = rate_state[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= rate_limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )
        bucket.append(now)
        return await call_next(request)

    if settings.enable_metrics:
        from prometheus_client import Counter, Histogram

        http_requests = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
        )
        http_latency = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency",
            ["method", "path"],
        )

        @app.middleware("http")
        async def metrics_middleware(request: Request, call_next):
            start = time.perf_counter()
            response = await call_next(request)
            duration = time.perf_counter() - start
            http_requests.labels(request.method, request.url.path, response.status_code).inc()
            http_latency.labels(request.method, request.url.path).observe(duration)
            return response

    # Routers
    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(chat_router, prefix="/chat", tags=["chat"])
    app.include_router(admin_router, prefix="/admin", tags=["admin"])
    app.include_router(users_router, prefix="/users", tags=["users"])
    app.include_router(farmers_router, prefix="/farmers", tags=["farmers"])
    app.include_router(conversations_router, prefix="/conversations", tags=["conversations"])
    app.include_router(documents_router, prefix="/documents", tags=["documents"])
    app.include_router(search_router, prefix="/search", tags=["search"])
    app.include_router(farms_router, prefix="/farms", tags=["farms"])
    app.include_router(crops_router, prefix="/crops", tags=["crops"])
    if settings.enable_metrics:
        app.include_router(metrics_router, prefix="/metrics", tags=["metrics"])

    return app


app = create_app()
