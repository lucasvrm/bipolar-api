import os
import logging
import time
from typing import Optional, Set
from fastapi import HTTPException, Header
from supabase import create_client, Client
from api.auth_fallback import supabase_get_user_http, should_use_fallback

logger = logging.getLogger("bipolar-api.dependencies")

__all__ = [
    "get_supabase_client",              # RESTAURADO (compatibilidade)
    "get_supabase_anon_auth_client",
    "get_supabase_service_role_client",
    "get_supabase_service",
    "verify_admin_authorization",
    "get_admin_emails",
]

# Cache (now using sync Client instead of AsyncClient)
_admin_emails_cache: Optional[Set[str]] = None
_cached_anon_client: Optional[Client] = None
_cached_service_client: Optional[Client] = None

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


def get_supabase_anon_auth_client() -> Client:
    """
    Cliente ANON síncrono para auth.get_user() e queries submetidas ao RLS.
    Cacheado para evitar custo de recreação em cada requisição.
    """
    global _cached_anon_client
    if _cached_anon_client is None:
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
        logger.info(f"Initializing ANON client (sync) with key: {anon_key[:5]}...{anon_key[-5:]}")

        _cached_anon_client = create_client(url, anon_key)
        logger.debug("Cliente ANON síncrono cacheado criado.")
    return _cached_anon_client


def get_supabase_service_role_client() -> Client:
    """
    Cliente SERVICE ROLE síncrono para operações administrativas (bypass RLS).
    NÃO usar para auth.get_user().
    """
    global _cached_service_client
    if _cached_service_client is None:
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
        logger.info(f"Initializing SERVICE client (sync) with key: {service_key[:5]}...{service_key[-5:]}")

        _cached_service_client = create_client(url, service_key)
        logger.debug("Cliente SERVICE ROLE síncrono cacheado criado.")
    return _cached_service_client


# Alias usado anteriormente em várias rotas (compatibilidade)
def get_supabase_client() -> Client:
    """
    Compatibilidade legado: retorna cliente ANON (RLS aplicado).
    Se uma rota antiga importar get_supabase_client, continua funcionando.
    """
    return get_supabase_anon_auth_client()


# Alias semântico para admin code existente
get_supabase_service = get_supabase_service_role_client


async def verify_admin_authorization(
    authorization: str = Header(None),
) -> bool:
    """
    Verifica token Bearer e se o e-mail está na lista ADMIN_EMAILS.
    Usa cliente ANON (correto para /auth/v1/user).
    
    Com fallback HTTP em caso de falha do cliente Supabase.
    """
    start_time = time.monotonic()
    
    if not authorization or not authorization.lower().startswith("bearer "):
        # Padrão: 401 para token ausente ou inválido
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    
    # Log início da verificação (apenas tamanho do token)
    logger.debug("Auth check start (Bearer token length=%d)", len(token))

    supabase_anon = get_supabase_anon_auth_client()

    user = None
    fallback_used = False
    
    try:
        # Tentativa primária com cliente Supabase
        user_resp = supabase_anon.auth.get_user(token)
        user = getattr(user_resp, "user", None)
        
    except Exception as e:
        error_str = str(e)
        
        # Check if we should use HTTP fallback
        if should_use_fallback(e):
            logger.warning(
                "Fallback HTTP auth.get_user acionado – erro na lib supabase: %s",
                error_str[:100]  # Only log first 100 chars
            )
            
            try:
                # TEMPORARY: HTTP fallback para contornar problemas do cliente async
                user_data = supabase_get_user_http(token)
                
                # Create a mock user object compatible with expected structure
                class MockUser:
                    def __init__(self, data):
                        self.email = data.get("email")
                        self.id = data.get("id")
                
                user = MockUser(user_data)
                fallback_used = True
                
            except Exception as fallback_error:
                logger.error("Fallback HTTP também falhou: %s", fallback_error)
                # Se fallback também falhar, token é inválido
                raise HTTPException(status_code=401, detail="Invalid or expired token")
        else:
            # Erro não é candidato a fallback (ex.: token realmente inválido)
            logger.error("Falha auth.get_user (sem fallback): %s", error_str[:100])
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = getattr(user, "email", None) if user else None

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

    # Log timing and success
    duration_ms = (time.monotonic() - start_time) * 1000
    logger.debug(
        "Auth check completed: email=%s, duration=%.2fms, fallback=%s",
        email,
        duration_ms,
        fallback_used
    )
    
    return True
