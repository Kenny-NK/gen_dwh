"""Main FastAPI application (T023, T026)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.health import router as health_router
from src.api.metrics import MetricsMiddleware, router as metrics_router
from src.api.openapi import (
    OPENAPI_DESCRIPTION,
    OPENAPI_SERVERS,
    OPENAPI_TAGS,
    SWAGGER_UI_PARAMETERS,
)
from src.api.router import api_router
from src.core.config import settings
from src.core.redis import redis_client
from src.core.security import invalidate_jwks_cache
from src.core.logging import setup_logging
from src.middleware.error_handler import register_error_handlers
from src.middleware.rate_limit import RateLimitMiddleware
from src.models.base import business_engine, system_engine

setup_logging(debug=settings.debug)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    invalidate_jwks_cache()
    await redis_client.aclose()
    await system_engine.dispose()
    await business_engine.dispose()


app = FastAPI(
    title="GenDWH API",
    description=OPENAPI_DESCRIPTION,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    servers=OPENAPI_SERVERS,
    swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(api_router)
