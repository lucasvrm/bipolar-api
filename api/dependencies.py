# em api/dependencies.py
import os
from fastapi import HTTPException
from supabase import acreate_client, AsyncClient

async def get_supabase_client() -> AsyncClient:
    """
    Dependency function assíncrona para criar e retornar um cliente Supabase.
    Isso garante que as variáveis de ambiente sejam lidas apenas quando
    a função é chamada, não na inicialização do módulo.
    """
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        # Se as variáveis de ambiente não estiverem configuradas no Render,
        # isso gerará um erro 500 claro em vez de um crash na inicialização.
        raise HTTPException(status_code=500, detail="Variáveis de ambiente do Supabase não configuradas no servidor.")

    supabase_options = {"persist_session": False}
    return await acreate_client(url, key, options=supabase_options)
