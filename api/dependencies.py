import os
import logging
from typing import Optional, Set
from fastapi import HTTPException, Header
from supabase import acreate_client, AsyncClient
from supabase.lib.client_options import AsyncClientOptions

logger = logging.getLogger("bipolar-api.dependencies")

__all__ = [
    "acreate_client",
    "AsyncClient",
    "get_supabase_client",              # RESTAURADO (compatibilidade)
    "get_supabase_anon_auth_client",
    "get_supabase_service_role_client",
    "get_supabase_service",
    "verify_admin_authorization",
    "get_admin_emails",
]

# Cache
_admin_emails_cache: Optional[Set[str]] = None
_cached_anon_client: Optional[AsyncClient] = None
_cached_service_client: Optional[AsyncClient] = None

# Heurísticas de validação
MIN_SERVICE_KEY_LENGTH = 180
MIN_ANON_KEY_LENGTH = 100


def get_admin_emails() -> Set[str]:
    global _admin_emails_cache
    if _admin_emails_cache is None:
        raw = os.getenv("ADMIN_EMAILS", "")
        _admin_emails_cache = {e.strip().lower() for e in raw.split(",") if e.strip()}
        logger.info("Cache de admin emails inicializado (%d)", len(_admin_emails_cache))
    return _admin_emails_cache


async def _create_anon_client() -> AsyncClient:
    url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()

    if not url or not anon_key:
        logger.error("SUPABASE_URL ou SUPABASE_ANON_KEY ausentes.")
        raise HTTPException(status_code=500, detail="Configuração Supabase incompleta (ANON).")

    # Validate length
    if len(anon_key) < MIN_ANON_KEY_LENGTH:
        logger.error("ANON KEY inválida/truncada (len=%d).", len(anon_key))
        raise HTTPException(status_code=500, detail="SUPABASE_ANON_KEY inválida ou truncada.")

    # Log masked key for debugging
    logger.info(f"Initializing ANON client with key: {anon_key[:5]}...{anon_key[-5:]}")

    options = AsyncClientOptions(persist_session=False, headers={"apikey": anon_key})
    return await acreate_client(url, anon_key, options=options)


async def _create_service_client() -> AsyncClient:
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

    if not url or not service_key:
        logger.error("SUPABASE_URL ou SUPABASE_SERVICE_KEY ausentes.")
        raise HTTPException(status_code=500, detail="Configuração Supabase incompleta (SERVICE).")

    # Validate length
    if len(service_key) < MIN_SERVICE_KEY_LENGTH:
        logger.error("SERVICE KEY inválida/truncada (len=%d).", len(service_key))
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_KEY inválida ou truncada.")

    # Log masked key for debugging
    logger.info(f"Initializing SERVICE client with key: {service_key[:5]}...{service_key[-5:]}")

    options = AsyncClientOptions(persist_session=False, headers={"apikey": service_key})
    return await acreate_client(url, service_key, options=options)


async def get_supabase_anon_auth_client() -> AsyncClient:
    """
    Cliente ANON para auth.get_user() e queries submetidas ao RLS.
    Cacheado para evitar custo de recreação em cada requisição.
    """
    global _cached_anon_client
    if _cached_anon_client is None:
        _cached_anon_client = await _create_anon_client()
        logger.debug("Cliente ANON cacheado criado.")
    return _cached_anon_client


async def get_supabase_service_role_client() -> AsyncClient:
    """
    Cliente SERVICE ROLE para operações administrativas (bypass RLS).
    NÃO usar para auth.get_user().
    """
    global _cached_service_client
    if _cached_service_client is None:
        _cached_service_client = await _create_service_client()
        logger.debug("Cliente SERVICE ROLE cacheado criado.")
    return _cached_service_client


# Alias usado anteriormente em várias rotas (compatibilidade)
async def get_supabase_client() -> AsyncClient:
    """
    Compatibilidade legado: retorna cliente ANON (RLS aplicado).
    Se uma rota antiga importar get_supabase_client, continua funcionando.
    """
    return await get_supabase_anon_auth_client()


# Alias semântico para admin code existente
get_supabase_service = get_supabase_service_role_client


async def verify_admin_authorization(
    authorization: str = Header(None),
) -> bool:
    """
    Verifica token Bearer e se o e-mail está na lista ADMIN_EMAILS.
    Usa cliente ANON (correto para /auth/v1/user).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        # Padrão: 401 para token ausente ou inválido
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()

    supabase_anon = await get_supabase_anon_auth_client()

    try:
        user_resp = await supabase_anon.auth.get_user(token)
    except Exception as e:
        error_str = str(e)
        # Check for configuration error
        if "Invalid API key" in error_str:
            logger.error(f"Configuration Error in verify_admin_authorization: {e}")
            raise HTTPException(status_code=500, detail="Internal Server Error: Database configuration invalid.")

        logger.error("Falha auth.get_user: %s", e)
        # Padrão: 401 para token inválido
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = getattr(user_resp, "user", None)
    email = getattr(user, "email", None)

    if not email:
        # Padrão: 401 para token sem email (inválido)
        raise HTTPException(status_code=401, detail="Invalid token payload")

    admin_emails = get_admin_emails()
    if not admin_emails:
        logger.warning("ADMIN_EMAILS vazio.")
        # Padrão: 403 para erro de configuração/permissão do lado do servidor/admin
        raise HTTPException(status_code=403, detail="Admin list not configured")

    if email.lower() not in admin_emails:
        # Padrão: 403 para usuário autenticado mas não autorizado
        raise HTTPException(status_code=403, detail="Not authorized as admin")

    return True
