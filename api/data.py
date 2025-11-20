# em api/data.py (Modificado para depuração com print)
import sys
import logging
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from .dependencies import get_supabase_client

# Logger específico para este módulo
logger = logging.getLogger("bipolar-api.data")

router = APIRouter(prefix="/data", tags=["Data Access"])

@router.get("/latest_checkin/{user_id}")
async def get_latest_checkin_for_user(user_id: str, supabase: Client = Depends(get_supabase_client)):
    """
    Busca o check-in mais recente com depuração máxima via print.
    """
    print("=" * 80, flush=True)
    print(f"[TENTATIVA 1 - DIAGNOSTIC] /data/latest_checkin/{user_id}", flush=True)
    print("=" * 80, flush=True)
    
    try:
        print(f"PASSO 1: Função iniciada para user_id: {user_id}", flush=True)
        print(f"PASSO 2: Tipo do cliente Supabase: {type(supabase)}", flush=True)
        print(f"PASSO 3: Métodos disponíveis: {[m for m in dir(supabase) if not m.startswith('_')][:10]}", flush=True)
        
        print("PASSO 4: Prestes a chamar o Supabase...", flush=True)
        
        # Esta linha está causando o erro - usando await em operação síncrona
        response = await supabase.table('check_ins').select('*').eq('user_id', user_id).order('checkin_date', ascending=False).limit(1).execute()
        
        print("PASSO 5: Chamada ao Supabase executada.", flush=True)
        
        if response.data:
            print(f"PASSO 6: Dados encontrados: {len(response.data)} registro(s)", flush=True)
            return response.data[0]
        else:
            print("PASSO 6: Nenhum dado encontrado na resposta.", flush=True)
            return None

    except Exception as e:
        print("=" * 80, flush=True)
        print(f"[ERRO CAPTURADO EM DATA.PY]", flush=True)
        print(f"Tipo de erro: {type(e).__name__}", flush=True)
        print(f"Mensagem: {str(e)}", flush=True)
        print("=" * 80, flush=True)
        
        # Re-raise para que o handler global capture com traceback completo
        raise
