"""FastAPI Application Entry Point.

Configures CORS, registers API routers, and exposes health check telemetry.
"""
from fastapi import FastAPI, Depends, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.database import get_db
from app.routers import jobs, analytics

app = FastAPI(
    title="Beep Job Aggregator API",
    description="REST API for Indian tech jobs, deduplication telemetry, and LLM classification cost tracking.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure Cross-Origin Resource Sharing (CORS)
# Uses explicit origins and does not enable credentialed cross-origin requests unnecessarily
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Register Feature Routers
app.include_router(jobs.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")


@app.get("/", tags=["System"])
def root_info():
    """Root info endpoint providing service metadata."""
    return {
        "service": "Beep Job Aggregator API",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
        "endpoints": {
            "health": "/api/health",
            "jobs": "/api/jobs",
            "job_filters": "/api/jobs/filters",
            "analytics": "/api/analytics"
        }
    }


@app.get("/api/health", tags=["System"])
def health_check(response: Response, db: Session = Depends(get_db)):
    """Health check verifying database connectivity and API uptime.
    
    Returns HTTP 200 when connected, or HTTP 503 when the database is unreachable.
    """
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "degraded",
            "database": db_status,
            "environment": settings.ENV,
            "pricing_tier": settings.GEMINI_PRICING_TIER
        }

    return {
        "status": "healthy",
        "database": db_status,
        "environment": settings.ENV,
        "pricing_tier": settings.GEMINI_PRICING_TIER
    }
