# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importa nossos módulos da API
from api import clinical, behavior, insights
from api.models import load_models

# Cria a instância principal da aplicação
app = FastAPI(
    title="Bipolar Prediction & Insights API",
    description="Um ecossistema de IA para análise e previsão do transtorno bipolar.",
    version="2.0.0"
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


# --- Endpoint Raiz para Health Check ---
@app.get("/", tags=["Health Check"])
def read_root():
    """Verifica se a API está online e saudável."""
    return {
        "message": "Bipolar Prediction & Insights API v2.0 is running",
        "status": "healthy"
    }
