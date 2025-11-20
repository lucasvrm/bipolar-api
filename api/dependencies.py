# em api/dependencies.py
import os
import logging
from fastapi import HTTPException
from supabase import acreate_client, AsyncClient

logger = logging.getLogger("bipolar-api.dependencies")

async def get_supabase_client() -> AsyncClient:
    """
    Dependency function assíncrona para criar e retornar um cliente Supabase.
    Isso garante que as variáveis de ambiente sejam lidas apenas quando
    a função é chamada, não na inicialização do módulo.
    """
    print("[DEPENDENCY] Iniciando criação do cliente Supabase...", flush=True)
    
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        # Se as variáveis de ambiente não estiverem configuradas no Render,
        # isso gerará um erro 500 claro em vez de um crash na inicialização.
        error_msg = "Variáveis de ambiente do Supabase não configuradas no servidor."
        print(f"[DEPENDENCY ERROR] {error_msg}", flush=True)
        raise HTTPException(status_code=500, detail=error_msg)

    print(f"[DEPENDENCY] URL encontrada: {url[:30]}...", flush=True)
    print(f"[DEPENDENCY] Key encontrada: {'*' * 10}", flush=True)
    
    supabase_options = {"persist_session": False}
    client = await acreate_client(url, key, options=supabase_options)
    
    print(f"[DEPENDENCY] Cliente criado com sucesso. Tipo: {type(client)}", flush=True)
    
    return client
