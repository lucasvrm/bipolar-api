# main.py
import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Importa nossos módulos da API
from api import clinical, behavior, insights, data
from api.models import load_models

# Configurar logging para capturar exceções
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("bipolar-api")

# Cria a instância principal da aplicação
app = FastAPI(
    title="Bipolar Prediction & Insights API",
    description="Um ecossistema de IA para análise e previsão do transtorno bipolar.",
    version="2.0.0"
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

# Evento que roda na inicialização da API
@app.on_event("startup")
def startup_event():
    """Carrega os modelos de IA ao iniciar a API."""
    load_models()

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


# --- Endpoint Raiz para Health Check ---
@app.get("/", tags=["Health Check"])
def read_root():
    """Verifica se a API está online e saudável."""
    return {
        "message": "Bipolar Prediction & Insights API v2.0 is running",
        "status": "healthy"
    }
