# em api/data.py (Modificado para depuração com print)
import logging
from fastapi import APIRouter, Depends, Request
from supabase import Client
from postgrest.exceptions import APIError
from api.dependencies import get_supabase_client
from api.utils import validate_uuid_or_400, handle_postgrest_error
from api.rate_limiter import limiter, DATA_ACCESS_RATE_LIMIT

# Logger específico para este módulo
logger = logging.getLogger("bipolar-api.data")

router = APIRouter(prefix="/data", tags=["Data Access"])

@router.get("/latest_checkin/{user_id}")
@limiter.limit(DATA_ACCESS_RATE_LIMIT)
async def get_latest_checkin_for_user(
    request: Request,
    user_id: str,
    supabase: Client = Depends(get_supabase_client)
):
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
        # Note: Using select('*') to retrieve all columns for flexibility
        # The prediction models may require different fields depending on the analysis type
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
