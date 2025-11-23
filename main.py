# main.py
import logging
import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Importa routers após criar app (ordem correta virá abaixo)
from api import clinical, behavior, insights, data, predictions, privacy, admin, account
from api.models import load_models
from api.middleware import ObservabilityMiddleware
from api.rate_limiter import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


# Configurar logging para capturar exceções
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("bipolar-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Models are loaded once at startup for efficient reuse across requests.
    """
    logger.info("=== Application Startup ===")

    # Log Supabase configuration (masked keys for security)
    supabase_url = os.getenv("SUPABASE_URL", "")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "")

    logger.warning(
        "SUPABASE_URL=%s ANON_PREFIX=%s SERVICE_PREFIX=%s",
        supabase_url,
        anon_key[:16] if anon_key else "(not set)",
        service_key[:16] if service_key else "(not set)"
    )

    load_models()
    logger.info("=== Application Ready ===")

    yield

    # Shutdown: Cleanup resources
    logger.info("=== Application Shutdown ===")
    try:
        from services.prediction_cache import get_cache
        cache = get_cache()
        await cache.close()
        logger.info("Cache connection closed")
    except Exception as e:
        logger.warning(f"Error closing cache: {e}")
    logger.info("=== Shutdown Complete ===")


# Cria a instância principal da aplicação
app = FastAPI(
    title="Bipolar Prediction & Insights API",
    description="Um ecossistema de IA para análise e previsão do transtorno bipolar.",
    version="2.0.0",
    lifespan=lifespan
)

# Attach rate limiter to app state
app.state.limiter = limiter

# Add rate limit exceeded handler
@app.exception_handler(RateLimitExceeded)
async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return rate_limit_exceeded_handler(request, exc)

# Handler global de exceções
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception: %s %s",
        request.method,
        request.url,
        exc_info=True
    )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# --- Configuração do CORS ---
ALLOWED_ORIGINS: List[str] = [
    "https://previso-fe.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
]

cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    for origin in cors_origins_env.split(","):
        origin = origin.strip()
        if origin and origin not in ALLOWED_ORIGINS:
            ALLOWED_ORIGINS.append(origin)

logger.info(f"CORS allowed origins: {ALLOWED_ORIGINS}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)

# Observabilidade
app.add_middleware(ObservabilityMiddleware)

# --- Inclusão dos Routers Modulares (após criar app) ---
app.include_router(clinical.router)
app.include_router(behavior.router)
app.include_router(insights.router)
app.include_router(data.router)
app.include_router(predictions.router)
app.include_router(privacy.router)
app.include_router(admin.router)
app.include_router(account.router)  # garante /api/profile e correlatos

# --- Endpoints de Health ---
@app.get("/", tags=["Health Check"])
def read_root():
    return {"message": "Bipolar Prediction & Insights API v2.0 is running", "status": "healthy"}

@app.get("/health", tags=["Health Check"])
def health_check():
    return {"status": "healthy", "uptime": "ok", "version": "2.0.0"}
