# em api/data.py (Modificado para depuração com print)
import sys # Importa o módulo sys para flush
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from .dependencies import get_supabase_client

router = APIRouter(prefix="/data", tags=["Data Access"])

@router.get("/latest_checkin/{user_id}")
async def get_latest_checkin_for_user(user_id: str, supabase: Client = Depends(get_supabase_client)):
    """
    Busca o check-in mais recente com depuração máxima via print.
    """
    print("--- [INÍCIO DA REQUISIÇÃO] ---", file=sys.stderr)
    sys.stderr.flush()
    
    try:
        print(f"PASSO 1: Função iniciada para user_id: {user_id}", file=sys.stderr)
        sys.stderr.flush()

        print("PASSO 2: Prestes a chamar o Supabase...", file=sys.stderr)
        sys.stderr.flush()
        
        response = await supabase.table('check_ins').select('*').eq('user_id', user_id).order('checkin_date', ascending=False).limit(1).execute()
        
        print("PASSO 3: Chamada ao Supabase executada.", file=sys.stderr)
        sys.stderr.flush()
        
        if response.data:
            print("PASSO 4: Dados encontrados na resposta.", file=sys.stderr)
            sys.stderr.flush()
            return response.data[0]
        else:
            print("PASSO 4: Nenhum dado encontrado na resposta.", file=sys.stderr)
            sys.stderr.flush()
            return None

    except Exception as e:
        print(f"--- [ERRO CRÍTICO] ---", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr) # Força a impressão do traceback
        sys.stderr.flush()
        raise HTTPException(status_code=500, detail="Erro interno. Verifique os logs do servidor.")
