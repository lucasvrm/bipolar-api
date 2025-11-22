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
    "get_supabase_anon_auth_client",
    "get_supabase_service_role_client",
    "get_supabase_service",
    "verify_admin_authorization",
    "get_admin_emails",
]

# Cache de e-mails admin
_admin_emails_cache: Optional[Set[str]] = None

# Limiares mínimos para validar se as chaves parecem corretas (heurística simples)
MIN_SERVICE_KEY_LENGTH = 180
MIN_ANON_KEY_LENGTH = 100


def get_admin_emails() -> Set[str]:
    """
    Lê ADMIN_EMAILS do ambiente, separa por vírgula e cacheia.
    """
    global _admin_emails_cache
    if _admin_emails_cache is None:
        raw = os.getenv("ADMIN_EMAILS", "")
        _admin_emails_cache = {e.strip().lower() for e in raw.split(",") if e.strip()}
        logger.info("Cache de admin emails inicializado com %d itens", len(_admin_emails_cache))
    return _admin_emails_cache


async def get_supabase_anon_auth_client() -> AsyncClient:
    """
    Cria cliente Supabase usando ANON KEY para validação de JWT de usuários (auth.get_user).
    NÃO usar para operações que exigem bypass de RLS.
    """
    url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not anon_key:
        logger.error("SUPABASE_URL ou SUPABASE_ANON_KEY ausentes no ambiente.")
        raise HTTPException(status_code=500, detail="Configuração Supabase incompleta (ANON).")

    if len(anon_key) < MIN_ANON_KEY_LENGTH:
        logger.error("ANON KEY inválida ou truncada (len=%d).", len(anon_key))
        raise HTTPException(status_code=500, detail="SUPABASE_ANON_KEY inválida ou truncada.")

    options = AsyncClientOptions(
        persist_session=False,
        headers={"apikey": anon_key},
    )
    client = await acreate_client(url, anon_key, options=options)
    logger.debug("Cliente ANON criado para validação de JWT.")
    return client


async def get_supabase_service_role_client() -> AsyncClient:
    """
    Cria cliente Supabase usando SERVICE ROLE KEY para operações administrativas (bypass RLS).
    NÃO usar para auth.get_user() — esse endpoint espera ANON KEY.
    """
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not service_key:
        logger.error("SUPABASE_URL ou SUPABASE_SERVICE_KEY ausentes no ambiente.")
        raise HTTPException(status_code=500, detail="Configuração Supabase incompleta (SERVICE).")

    if len(service_key) < MIN_SERVICE_KEY_LENGTH:
        logger.error("SERVICE KEY inválida ou truncada (len=%d).", len(service_key))
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_KEY inválida ou truncada.")

    options = AsyncClientOptions(
        persist_session=False,
        headers={"apikey": service_key},
    )
    client = await acreate_client(url, service_key, options=options)
    logger.debug("Cliente SERVICE ROLE criado para operações administrativas.")
    return client


# Alias para consistência com rotas existentes
get_supabase_service = get_supabase_service_role_client


async def verify_admin_authorization(
    authorization: str = Header(None),
    supabase_anon: AsyncClient = None,
) -> bool:
    """
    Verifica se o token Bearer corresponde a um usuário válido e se o e-mail
    está na lista de admin (ADMIN_EMAILS).

    Fluxo:
      1. Extrai bearer token.
      2. Usa cliente ANON (auth.get_user(token)).
      3. Confere e-mail no cache de admin.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()

    # Permitir injeção externa do cliente anon para testar / evitar recriação
    if supabase_anon is None:
        supabase_anon = await get_supabase_anon_auth_client()

    try:
        user_resp = await supabase_anon.auth.get_user(token)
    except Exception as e:
        logger.error("Falha auth.get_user: %s", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = getattr(user_resp, "user", None)
    email = getattr(user, "email", None)

    if not email:
        logger.warning("Token válido mas sem e-mail no payload.")
        raise HTTPException(status_code=401, detail="Invalid token payload")

    admin_emails = get_admin_emails()
    if not admin_emails:
        logger.warning("ADMIN_EMAILS vazio — nenhum admin reconhecido.")
        raise HTTPException(status_code=403, detail="Admin list not configured")

    if email.lower() not in admin_emails:
        raise HTTPException(status_code=403, detail="Not authorized as admin")

    return True
