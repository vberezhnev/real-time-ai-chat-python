from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.ws import close_all_ws_connections
from app.api.ws import router as ws_router
from app.config import settings
from app.core.logging import setup_logging
from app.core.metrics import MetricsMiddleware
from app.core.redis import close_redis, get_redis
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.session import dispose_engine, get_session_factory

setup_logging()

import structlog  # noqa: E402

logger = structlog.get_logger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    redis = await get_redis()
    await redis.ping()
    yield
    await close_all_ws_connections()
    await close_redis()
    await dispose_engine()


_rate_limiting_enabled = settings.environment not in ("test", "ci")
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_global],
    enabled=_rate_limiting_enabled,
)

app = FastAPI(title="Real-Time AI Chat", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if settings.is_prod:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(",") if settings.cors_origins != "*" else [],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MetricsMiddleware)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    clear_contextvars()
    bind_contextvars(
        request_id=request.headers.get("X-Request-ID", ""),
        method=request.method,
        path=request.url.path,
    )
    response = await call_next(request)
    bind_contextvars(status=response.status_code)
    return response


app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(ws_router)


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    db_ok = False
    redis_ok = False
    try:
        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.warning("health_db_failed", error=str(e))

    try:
        redis = await get_redis()
        await redis.ping()
        redis_ok = True
    except Exception as e:
        logger.warning("health_redis_failed", error=str(e))

    ok = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "healthy" if ok else "degraded",
            "database": "up" if db_ok else "down",
            "redis": "up" if redis_ok else "down",
        },
    )
