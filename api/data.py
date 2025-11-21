# em api/data.py (Modificado para depuração com print)
import logging
from fastapi import APIRouter, Depends
from supabase import AsyncClient
from postgrest.exceptions import APIError
from api.dependencies import get_supabase_client
from api.utils import validate_uuid_or_400, handle_postgrest_error

# Logger específico para este módulo
logger = logging.getLogger("bipolar-api.data")

router = APIRouter(prefix="/data", tags=["Data Access"])

@router.get("/latest_checkin/{user_id}")
async def get_latest_checkin_for_user(user_id: str, supabase: AsyncClient = Depends(get_supabase_client)):
    """
    Busca o check-in mais recente para o usuário especificado.
    
    Args:
        user_id: UUID do usuário
        supabase: Cliente Supabase injetado
        
    Returns:
        Dados do check-in mais recente ou None se não encontrado
    """
    # Validate UUID format
    validate_uuid_or_400(user_id, "user_id")
    
    logger.debug(f"Fetching latest check-in for user_id: {user_id}")
    
    try:
        response = await supabase.table('check_ins')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('checkin_date', desc=True)\
            .limit(1)\
            .execute()
        
        if response.data:
            logger.debug(f"Found {len(response.data)} check-in(s) for user_id: {user_id}")
            return response.data[0]
        else:
            logger.debug(f"No check-ins found for user_id: {user_id}")
            return None

    except APIError as e:
        # Handle PostgREST errors using centralized utility
        handle_postgrest_error(e, user_id)
    except Exception as e:
        logger.exception(f"Error fetching latest check-in for user_id={user_id}")
        raise
