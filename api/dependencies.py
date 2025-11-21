# em api/dependencies.py
import os
import logging
from fastapi import HTTPException
from supabase import acreate_client, AsyncClient
from supabase.lib.client_options import AsyncClientOptions

logger = logging.getLogger("bipolar-api.dependencies")

async def get_supabase_client() -> AsyncClient:
    """
    Dependency function assíncrona para criar e retornar um cliente Supabase.
    Isso garante que as variáveis de ambiente sejam lidas apenas quando
    a função é chamada, não na inicialização do módulo.
    """
    logger.debug("Creating Supabase client...")
    
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        error_msg = "Variáveis de ambiente do Supabase não configuradas no servidor."
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

    logger.debug(f"Supabase URL configured: {url[:30]}...")
    
    # Use AsyncClientOptions object instead of dict
    supabase_options = AsyncClientOptions(persist_session=False)
    client = await acreate_client(url, key, options=supabase_options)
    
    logger.debug(f"Supabase client created successfully: {type(client).__name__}")
    
    return client
