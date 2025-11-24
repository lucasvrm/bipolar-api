import os
import logging
import time
import threading
from typing import Optional, Set
from fastapi import HTTPException, Header
from supabase import create_client, Client

logger = logging.getLogger("bipolar-api.dependencies")

__all__ = [
    "get_supabase_anon_client",         # Nome explícito para cliente ANON
    "get_supabase_client",              # LEGADO: retorna ANON (mantido para compatibilidade)
    "get_supabase_anon_auth_client",
    "get_supabase_service_role_client",
    "get_supabase_service",             # Alias para service role
    "verify_admin_authorization",
    "get_admin_emails",
    "acreate_client",                   # SHIM para testes
    "reset_caches_for_testing",         # Utility para testes
]

# Cache de clientes e locks para thread-safety
_admin_emails_cache: Optional[Set[str]] = None
_cached_anon_client: Optional[Client] = None
_cached_service_client: Optional[Client] = None

# Thread locks para inicialização thread-safe
_client_initialization_lock = threading.Lock()
_admin_emails_initialization_lock = threading.Lock()

# Heurísticas simples de sanidade (ajustáveis conforme formato das keys)
MIN_SERVICE_KEY_LENGTH = 180
MIN_ANON_KEY_LENGTH = 100


def get_admin_emails() -> Set[str]:
    """
    Thread-safe getter para emails de administradores.
    Usa double-checked locking para performance.
    """
    global _admin_emails_cache
    if _admin_emails_cache is None:
        with _admin_emails_initialization_lock:
            if _admin_emails_cache is None:  # Double-check
                raw = os.getenv("ADMIN_EMAILS", "")
                _admin_emails_cache = {e.strip().lower() for e in raw.split(",") if e.strip()}
                logger.info("Cache de admin emails inicializado (%d)", len(_admin_emails_cache))
    return _admin_emails_cache


def reset_caches_for_testing():
    """
    Utility para resetar caches globais em testes.
    NÃO usar em código de produção.
    """
    global _admin_emails_cache, _cached_anon_client, _cached_service_client
    _admin_emails_cache = None
    _cached_anon_client = None
    _cached_service_client = None



def acreate_client(url: str, key: str, options=None):
    """
    SHIM para compatibilidade com testes que ainda patcham acreate_client.
    Retorna um cliente síncrono padrão. 'options' ignorado.
    """
    return create_client(url, key)


def get_supabase_anon_auth_client() -> Client:
    """
    Cliente ANON (RLS aplicado). Usado para operações que dependem do contexto do usuário (ex.: auth.get_user).
    Thread-safe com double-checked locking.
    """
    global _cached_anon_client
    if _cached_anon_client is None:
        with _client_initialization_lock:
            if _cached_anon_client is None:  # Double-check
                url = os.getenv("SUPABASE_URL")
                anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()

                if not url or not anon_key:
                    logger.error("SUPABASE_URL ou SUPABASE_ANON_KEY ausentes.")
                    raise HTTPException(status_code=500, detail="Configuração Supabase incompleta (ANON).")

                if len(anon_key) < MIN_ANON_KEY_LENGTH:
                    logger.error("ANON KEY inválida/truncada (len=%d).", len(anon_key))
                    raise HTTPException(status_code=500, detail="SUPABASE_ANON_KEY inválida ou truncada.")

                logger.info("Inicializando cliente ANON (sync) key=%s...%s", anon_key[:5], anon_key[-5:])
                _cached_anon_client = acreate_client(url, anon_key)
                logger.debug("Cliente ANON cacheado.")
    return _cached_anon_client


def get_supabase_service_role_client() -> Client:
    """
    Cliente SERVICE ROLE (bypass RLS). Usado em endpoints administrativos (/api/admin/...).
    NÃO utilizar para operações sensíveis ao contexto do usuário final (ex.: auth.get_user).
    Thread-safe com double-checked locking.
    """
    global _cached_service_client
    if _cached_service_client is None:
        with _client_initialization_lock:
            if _cached_service_client is None:  # Double-check
                url = os.getenv("SUPABASE_URL")
                service_key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

                if not url or not service_key:
                    logger.error("SUPABASE_URL ou SUPABASE_SERVICE_KEY ausentes.")
                    raise HTTPException(status_code=500, detail="Configuração Supabase incompleta (SERVICE).")

                if len(service_key) < MIN_SERVICE_KEY_LENGTH:
                    logger.error("SERVICE KEY inválida/truncada (len=%d).", len(service_key))
                    raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_KEY inválida ou truncada.")

                logger.info("Inicializando cliente SERVICE (sync) key=%s...%s", service_key[:5], service_key[-5:])
                _cached_service_client = acreate_client(url, service_key)
                logger.debug("Cliente SERVICE ROLE cacheado.")
    return _cached_service_client


def get_supabase_anon_client() -> Client:
    """
    Nome explícito para cliente ANON (RLS aplicado).
    Use este para operações de usuários regulares.
    """
    return get_supabase_anon_auth_client()


def get_supabase_client() -> Client:
    """
    Compatibilidade legado: retorna cliente ANON.
    DEPRECATED: Use get_supabase_anon_client() para clareza.
    """
    return get_supabase_anon_auth_client()


# Alias semântico para código admin existente
get_supabase_service = get_supabase_service_role_client


async def verify_admin_authorization(
    authorization: str = Header(None),
) -> bool:
    """
    Verifica se o token Bearer é válido e se o usuário é admin (e-mail listado ou user_metadata.role=admin).

    Etapas:
      1. Verifica configuração (ANON).
      2. Verifica formato do header Authorization.
      3. Usa Supabase auth.get_user(token).
      4. Checa email OU user_metadata.role == admin.
    """
    start_time = time.monotonic()

    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()

    if not supabase_url or not anon_key:
        logger.error("Configuração Supabase incompleta: URL ou ANON_KEY ausente")
        raise HTTPException(status_code=500, detail="Configuração do servidor incompleta.")

    if not authorization or not authorization.lower().startswith("bearer "):
        logger.warning("Authorization ausente/malformatado")
        raise HTTPException(status_code=401, detail="Token de autorização ausente ou inválido")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        logger.warning("Token vazio")
        raise HTTPException(status_code=401, detail="Token vazio")

    logger.debug("Admin auth check start (token length=%d)", len(token))

    supabase_anon = get_supabase_anon_auth_client()

    try:
        user_resp = supabase_anon.auth.get_user(token)
        user = getattr(user_resp, "user", None)
        if not user:
            logger.warning("Sem user no response")
            raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Falha Supabase auth: %s", str(e)[:200])
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    email = getattr(user, "email", None)
    if not email:
        logger.warning("User sem email")
        raise HTTPException(status_code=401, detail="Token sem email válido")

    admin_emails = get_admin_emails()
    user_metadata = getattr(user, "user_metadata", {}) or {}
    user_role = user_metadata.get("role", "").lower() if isinstance(user_metadata, dict) else ""

    is_admin_by_email = email.lower() in admin_emails if admin_emails else False
    is_admin_by_role = user_role == "admin"

    if not (is_admin_by_email or is_admin_by_role):
        logger.info("User não autorizado: email=%s role=%s admin_emails=%d", email, user_role, len(admin_emails))
        raise HTTPException(status_code=403, detail="Acesso negado.")

    duration_ms = (time.monotonic() - start_time) * 1000
    logger.info(
        "Admin auth OK: email=%s role=%s by_email=%s by_role=%s duration=%.2fms",
        email, user_role, is_admin_by_email, is_admin_by_role, duration_ms
    )
    return True
