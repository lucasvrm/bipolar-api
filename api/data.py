# api/data.py
import os
import logging
from fastapi import APIRouter, HTTPException
from supabase import create_client, Client, ClientOptions

# Configurar logger para este módulo
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["Data Access"])

# Inicializa o cliente Supabase com bypass de RLS
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")

# Apenas cria o cliente se as variáveis de ambiente estiverem configuradas
if url and key:
    supabase_options = ClientOptions(persist_session=False)
    supabase: Client = create_client(url, key, options=supabase_options)
else:
    supabase = None

@router.get("/latest_checkin/{user_id}")
def get_latest_checkin_for_user(user_id: str):
    """
    Busca o check-in mais recente para um ID de usuário específico.
    Esta rota age como um proxy seguro, usando o poder de admin da API.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Serviço de banco de dados não está disponível. Configure SUPABASE_URL e SUPABASE_SERVICE_KEY.")
    
    # Validação básica do user_id
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id não pode estar vazio.")
    
    try:
        # Busca dados da tabela 'check_ins' selecionando apenas campos necessários
        response = supabase.table('check_ins').select('id, user_id, checkin_date, mood, energy, sleep_hours, medication_taken, notes').eq('user_id', user_id).order('checkin_date', ascending=False).limit(1).execute()
        
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
