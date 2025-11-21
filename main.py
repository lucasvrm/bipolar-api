# main.py
import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Importa nossos módulos da API
from api import clinical, behavior, insights, data, predictions
from api.models import load_models

# Configurar logging para capturar exceções
# NOTE: DEBUG level enabled for diagnostic purposes during initial deployment
# Consider changing to logging.INFO for production after issue is resolved
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("bipolar-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Models are loaded once at startup for efficient reuse across requests.
    """
    # Startup: Load models
    logger.info("=== Application Startup ===")
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

# Handler global de exceções para diagnóstico completo
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Captura todas as exceções não tratadas e loga traceback completo.
    Isso garante que erros sejam visíveis nos logs do Render para diagnóstico.
    """
    logger.exception(
        "Unhandled exception occurred while handling request: %s %s",
        request.method,
        request.url
    )
    
    # Força impressão do traceback completo para stderr (visível no Render)
    tb = traceback.format_exc()
    print("=" * 80, flush=True)
    print("EXCEPTION TRACEBACK:", flush=True)
    print(tb, flush=True)
    print("=" * 80, flush=True)
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error - Check logs for details"}
    )


# --- Configuração do CORS ---
origins = [
    "https://previso-fe.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Inclusão dos Routers Modulares ---
app.include_router(clinical.router)
app.include_router(behavior.router)
app.include_router(insights.router)
app.include_router(data.router)
app.include_router(predictions.router)


# --- Endpoint Raiz para Health Check ---
@app.get("/", tags=["Health Check"])
def read_root():
    """Verifica se a API está online e saudável."""
    return {
        "message": "Bipolar Prediction & Insights API v2.0 is running",
        "status": "healthy"
    }
