import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("hospital_system")

from app.core.redis import redis_manager
from app.routers.events import ws_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager handling startup & shutdown."""
    logger.info("Initializing Hospital Command Center Backend...")
    await init_db()
    logger.info("Database connection established.")
    await redis_manager.initialize()
    yield
    logger.info("Shutting down Hospital Command Center Backend...")
    await ws_manager.close_all()
    await redis_manager.close()

is_production = settings.ENVIRONMENT.lower() in ["production", "prod"]
show_docs = (not is_production) or settings.ENABLE_PROD_DOCS

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-Grade Multi-Agent AI System for Hospital Resource Optimization, Clinical Workflow Automation, and Patient Care Coordination.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if show_docs else None,
    redoc_url="/redoc" if show_docs else None,
    openapi_url="/openapi.json" if show_docs else None
)

# Configure CORS Middleware (Configurable Allowlist, no wildcard with credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Production Middlewares
from app.middleware import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    InputSanitizationMiddleware,
    InMemoryRateLimiter
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(InputSanitizationMiddleware)
app.add_middleware(
    InMemoryRateLimiter,
    max_requests=settings.RATE_LIMIT_PER_MINUTE,
    window_seconds=60
)

# Import Routers
from app.routers import (
    auth, patients, beds, diseases, emergencies, approvals,
    staff, equipment, audit, dashboard, workflows, predictions, system, events, intake, intelligence,
    documents, investigations, clinical_priority, observations
)

# Include REST Routers under API V1 Prefix
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(patients.router, prefix=settings.API_V1_STR)
app.include_router(observations.router, prefix=settings.API_V1_STR)
app.include_router(intake.router, prefix=settings.API_V1_STR)
app.include_router(intelligence.router, prefix=settings.API_V1_STR)
app.include_router(clinical_priority.router, prefix=settings.API_V1_STR)
app.include_router(documents.router, prefix=settings.API_V1_STR)
app.include_router(investigations.router, prefix=settings.API_V1_STR)
app.include_router(beds.router, prefix=settings.API_V1_STR)
app.include_router(diseases.router, prefix=settings.API_V1_STR)
app.include_router(emergencies.router, prefix=settings.API_V1_STR)
app.include_router(approvals.router, prefix=settings.API_V1_STR)
app.include_router(staff.router, prefix=settings.API_V1_STR)
app.include_router(equipment.router, prefix=settings.API_V1_STR)
app.include_router(audit.router, prefix=settings.API_V1_STR)
app.include_router(dashboard.router, prefix=settings.API_V1_STR)
app.include_router(workflows.router, prefix=settings.API_V1_STR)
app.include_router(predictions.router, prefix=settings.API_V1_STR)
app.include_router(system.router, prefix=settings.API_V1_STR)

# Include WebSocket Router (no API prefix — connects at /ws/events)
app.include_router(events.router)

from sqlalchemy import text
from fastapi.responses import JSONResponse
from fastapi import Request
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches unhandled internal exceptions to prevent leaking tracebacks, database schema details,
    or sensitive memory data to client callers. Logs the error securely on the server.
    """
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    logger.error(f"Unhandled server exception on {request.method} {request.url.path}: {exc.__class__.__name__}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please contact system support."}
    )

@app.get("/", tags=["System"])
async def root():
    return {
        "status": "online",
        "system": settings.PROJECT_NAME,
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "docs": "/docs" if show_docs else "DISABLED_IN_PRODUCTION"
    }

@app.get("/health", tags=["System"])
@app.get(f"{settings.API_V1_STR}/health", tags=["System"])
async def health_check():
    """
    Active Health Probe: Executes async ping against database and Redis.
    Returns 200 OK if healthy/operational, or 503 Service Unavailable if database degraded.
    """
    db_status = "connected"
    is_healthy = True
    try:
        from app.database import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning(f"Database health probe failed: {exc}")
        db_status = "unreachable"
        is_healthy = False

    redis_alive = await redis_manager.ping()
    redis_status = "connected" if redis_alive else "unreachable"

    payload = {
        "status": "healthy" if is_healthy else "degraded",
        "database": db_status,
        "redis": redis_status,
        "environment": settings.ENVIRONMENT,
        "redis_configured": bool(settings.REDIS_URL),
        "llm_enabled": bool(settings.OPENAI_API_KEY or settings.GROQ_API_KEY)
    }
    return JSONResponse(
        content=payload,
        status_code=200 if is_healthy else 503
    )
