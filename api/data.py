# em api/data.py (Refatorado)
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from .dependencies import get_supabase_client

router = APIRouter(prefix="/data", tags=["Data Access"])

@router.get("/latest_checkin/{user_id}")
def get_latest_checkin_for_user(user_id: str, supabase: Client = Depends(get_supabase_client)):
    """
    Busca o check-in mais recente usando um cliente Supabase injetado.
    """
    try:
        response = supabase.table('check_ins').select('*').eq('user_id', user_id).order('checkin_date', ascending=False).limit(1).execute()
        
        if response.data:
            return response.data[0]
        else:
            return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno ao buscar dados: {str(e)}")
