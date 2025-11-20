# em api/data.py (Refatorado)
import logging
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from .dependencies import get_supabase_client

# Configurar logger para este módulo
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["Data Access"])

@router.get("/latest_checkin/{user_id}")
def get_latest_checkin_for_user(user_id: str, supabase: Client = Depends(get_supabase_client)):
    """
    Busca o check-in mais recente para um ID de usuário específico.
    Esta rota age como um proxy seguro, usando o poder de admin da API.
    """
    # Validação básica do user_id
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id não pode estar vazio.")
    
    try:
        # Busca dados da tabela 'check_ins' selecionando todos os campos
        response = supabase.table('check_ins').select('*').eq('user_id', user_id).order('checkin_date', ascending=False).limit(1).execute()
        
        if response.data:
            return response.data[0]
        else:
            # Retorna um 200 OK com corpo nulo se não houver check-ins,
            # o frontend está preparado para isso.
            return None
    except Exception as e:
        # Log completo do erro no servidor
        logger.error(f"Erro ao buscar check-in para user_id {user_id}: {str(e)}", exc_info=True)
        # Retorna mensagem genérica ao cliente
        raise HTTPException(status_code=500, detail="Erro interno ao buscar dados.")
