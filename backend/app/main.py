from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings, validate_runtime_settings

settings = get_settings()
validate_runtime_settings(settings)

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("fieldsense")

app = FastAPI(
    title="FieldSense",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

origins = settings.cors_origin_list
if not origins:
    origins = ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    detail = "Internal server error"
    if not settings.is_production:
        detail = f"{type(exc).__name__}: {exc}"
    return JSONResponse(status_code=500, content={"detail": detail})


@app.get("/")
def root():
    return {
        "name": "FieldSense",
        "env": settings.app_env,
        "docs": "/docs" if not settings.is_production else None,
        "health": "/health/live",
    }


@app.on_event("startup")
def on_startup():
    if settings.is_production and settings.demo_user_picker_enabled:
        logger.warning(
            "DEMO_USER_PICKER_ENABLED=true in production — demo identity is not real authentication."
        )
