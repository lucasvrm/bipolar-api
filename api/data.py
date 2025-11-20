# em api/data.py (Refatorado para Logging)
import logging # Importa o módulo de logging
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from .dependencies import get_supabase_client

# Configura um logger básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["Data Access"])

@router.get("/latest_checkin/{user_id}")
def get_latest_checkin_for_user(user_id: str, supabase: Client = Depends(get_supabase_client)):
    """
    Busca o check-in mais recente usando um cliente Supabase injetado
    e registra exceções detalhadas em caso de falha.
    """
    try:
        logger.info(f"Buscando check-in para user_id: {user_id}")
        response = supabase.table('check_ins').select('*').eq('user_id', user_id).order('checkin_date', ascending=False).limit(1).execute()
        
        # Checagem de erro pós-requisição (se a API do Supabase retornar erro)
        # if hasattr(response, 'error') and response.error:
        #     raise Exception(response.error.message)

        logger.info(f"Resposta do Supabase para user_id {user_id}: {'Dados encontrados' if response.data else 'Nenhum dado encontrado'}")
        
        if response.data:
            return response.data[0]
        else:
            return None

    except Exception as e:
        # ESTA É A MUDANÇA CRUCIAL:
        # Loga o traceback completo da exceção no console do Render.
        logger.exception(f"Falha crítica ao buscar dados para user_id {user_id}: {e}")
        
        # Levanta o erro HTTP para notificar o frontend.
        raise HTTPException(status_code=500, detail="Ocorreu um erro interno no servidor ao processar sua solicitação.")
