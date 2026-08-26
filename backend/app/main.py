import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.seed_data import seed_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("hospital_system")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager handling startup & shutdown."""
    logger.info("Initializing Hospital Command Center Backend...")
    await init_db()
    await seed_database()
    logger.info("Database & Synthetic Seed Data initialized.")
    yield
    logger.info("Shutting down Hospital Command Center Backend...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-Grade Multi-Agent AI System for Hospital Resource Optimization, Clinical Workflow Automation, and Patient Care Coordination.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production setup allows configurable domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Production Middlewares
from app.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Import Routers
from app.routers import (
    auth, patients, beds, diseases, emergencies, approvals,
    staff, equipment, audit, dashboard, workflows, predictions, system, events
)

# Include REST Routers under API V1 Prefix
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(patients.router, prefix=settings.API_V1_STR)
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

@app.get("/", tags=["System"])
async def root():
    return {
        "status": "online",
        "system": settings.PROJECT_NAME,
        "version": "1.0.0",
        "mode": "ENTERPRISE_DEPLOYABLE",
        "docs": "/docs"
    }

@app.get("/health", tags=["System"])
@app.get(f"{settings.API_V1_STR}/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "redis_configured": bool(settings.REDIS_URL),
        "llm_enabled": bool(settings.OPENAI_API_KEY or settings.GROQ_API_KEY)
    }
