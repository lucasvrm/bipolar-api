"""
Account / Profile endpoints.

Responsabilidades:
- Recuperar perfil autenticado (fallback quando RLS quebrar para SELECT direto no frontend).
- Atualizar dados básicos do perfil (restrito ao próprio usuário).
- (Opcional) promover usuário a admin (apenas se já for admin ou se ambiente permitir).
- Expor um resumo agregado simples (check-ins recentes, contagens) para o dashboard.

Observações de Segurança:
- Validação de token sempre via cliente ANON (respeita assinatura JWT).
- Operações de leitura/escrita usam client SERVICE ROLE para evitar falhas de RLS intermitentes,
  mas com checagens explícitas do user_id para não abrir acesso indevido.
- Se quiser manter RLS estrito, substituir get_supabase_service() por get_supabase_anon_auth_client()
  nas operações que não exigem bypass (ex.: leitura simples do próprio perfil).
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Header, Body
from supabase import Client
from postgrest.exceptions import APIError

from api.dependencies import (
    get_supabase_service,
    get_supabase_anon_auth_client,
)

router = APIRouter(prefix="/api", tags=["Account"])
logger = logging.getLogger("bipolar-api.account")


# =====================================================================================
# Helpers
# =====================================================================================

def _extract_user_id(supabase_anon: Client, token: str) -> str:
    """
    Valida token com cliente ANON e extrai user_id (UUID).
    Lança HTTP 401 se inválido.
    """
    try:
        auth_resp = supabase_anon.auth.get_user(token)
        user = getattr(auth_resp, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Token inválido ou expirado")
        user_id = getattr(user, "id", None) or getattr(user, "uuid", None)
        if not user_id:
            raise HTTPException(status_code=400, detail="Usuário sem ID válido")
        return user_id
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[Account] Falha ao validar token: {e}")
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")


def _get_profile(service_client: Client, user_id: str) -> Dict[str, Any]:
    """
    Recupera perfil pelo id usando CLIENT SERVICE (bypass RLS).
    Lança 404 se não encontrado.
    """
    try:
        resp = service_client.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        data = resp.data or []
        if not data:
            raise HTTPException(status_code=404, detail="Perfil não encontrado")
        return data[0]
    except HTTPException:
        raise
    except APIError as e:
        logger.exception("[Account] Erro PostgREST ao buscar perfil")
        raise HTTPException(status_code=500, detail=f"Erro banco (profiles): {e}")
    except Exception as e:
        logger.exception("[Account] Erro inesperado ao buscar perfil")
        raise HTTPException(status_code=500, detail=f"Erro inesperado (profiles): {e}")


def _is_admin_profile(profile: Dict[str, Any]) -> bool:
    return (profile.get("role") == "admin")


# =====================================================================================
# GET /api/profile  - Perfil autenticado
# =====================================================================================
@router.get("/profile")
async def get_own_profile(
    authorization: str = Header(None),
    supabase_service: Client = Depends(get_supabase_service),
    supabase_anon: Client = Depends(get_supabase_anon_auth_client),
):
    """
    Retorna o perfil do usuário autenticado.
    - Valida token com ANON.
    - Busca perfil via SERVICE para contornar possíveis problemas temporários de RLS.
    - (Opcional) autopromoção removida por segurança; só promover via endpoint dedicado.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou malformado")

    token = authorization.split(" ", 1)[1].strip()
    user_id = _extract_user_id(supabase_anon, token)

    profile = _get_profile(supabase_service, user_id)

    return {
        "status": "success",
        "profile": profile
    }


# =====================================================================================
# PATCH /api/profile - Atualiza campos próprios
# =====================================================================================
@router.patch("/profile")
async def update_own_profile(
    authorization: str = Header(None),
    payload: Dict[str, Any] = Body(...),
    supabase_service: Client = Depends(get_supabase_service),
    supabase_anon: Client = Depends(get_supabase_anon_auth_client),
):
    """
    Atualiza campos simples do próprio perfil.
    Campos permitidos: full_name, avatar_url, timezone, preferences (json), locale.
    Ignora alterações em: role, is_test_patient, source.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou malformado")
    token = authorization.split(" ", 1)[1].strip()
    user_id = _extract_user_id(supabase_anon, token)

    # Filtrar campos permitidos
    allowed_keys = {"full_name", "avatar_url", "timezone", "preferences", "locale"}
    update_data = {k: v for k, v in payload.items() if k in allowed_keys}

    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo permitido para atualização encontrado.")

    try:
        resp = supabase_service.table("profiles").update(update_data).eq("id", user_id).execute()
        data = resp.data or []
        if not data:
            raise HTTPException(status_code=404, detail="Perfil não encontrado para atualização")
        return {
            "status": "success",
            "updated": data[0]
        }
    except HTTPException:
        raise
    except APIError as e:
        logger.exception("[Account] Erro PostgREST update perfil")
        raise HTTPException(status_code=500, detail=f"Erro banco ao atualizar perfil: {e}")
    except Exception as e:
        logger.exception("[Account] Erro inesperado update perfil")
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {e}")


# =====================================================================================
# POST /api/profile/promote - Promove perfil a admin (restrito)
# =====================================================================================
@router.post("/profile/promote")
async def promote_to_admin(
    authorization: str = Header(None),
    supabase_service: Client = Depends(get_supabase_service),
    supabase_anon: Client = Depends(get_supabase_anon_auth_client),
):
    """
    Promove usuário autenticado a admin se:
    - Já for admin (idempotente), ou
    - Variável ALLOW_SELF_ADMIN_PROMOTE=1 estiver setada (ambiente controlado de migração inicial).
    NÃO expor em produção sem controle.

    Retorna perfil atualizado.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou malformado")
    token = authorization.split(" ", 1)[1].strip()
    user_id = _extract_user_id(supabase_anon, token)

    profile = _get_profile(supabase_service, user_id)

    if _is_admin_profile(profile):
        return {"status": "success", "message": "Já é admin", "profile": profile}

    allow_env = ( ( (val:= ( (lambda x: x if x else None)( 
        (lambda v: v.strip() if v else v)( 
            __import__("os").getenv("ALLOW_SELF_ADMIN_PROMOTE")
        ) )) ) is not None ) and val == "1" )

    # (Uso de expressão para reforçar que só promove se alavanca for explícita)
    if not allow_env:
        raise HTTPException(status_code=403, detail="Promoção a admin não permitida. Set ALLOW_SELF_ADMIN_PROMOTE=1 para habilitar.")

    try:
        upd = supabase_service.table("profiles").update({"role": "admin"}).eq("id", user_id).execute()
        data = upd.data or []
        if not data:
            raise HTTPException(status_code=500, detail="Falha ao promover perfil (sem retorno).")
        # Auditoria (best-effort)
        try:
            supabase_service.table("audit_log").insert({
                "action": "promote_admin",
                "details": {"user_id": user_id, "previous_role": profile.get("role"), "new_role": "admin"},
            }).execute()
        except Exception:
            logger.warning("[Account] Falha auditoria promote_admin (ignorado)")
        return {
            "status": "success",
            "message": "Perfil promovido a admin",
            "profile": data[0]
        }
    except HTTPException:
        raise
    except APIError as e:
        logger.exception("[Account] Erro banco ao promover admin")
        raise HTTPException(status_code=500, detail=f"Erro banco: {e}")
    except Exception as e:
        logger.exception("[Account] Erro inesperado promoção admin")
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {e}")


# =====================================================================================
# GET /api/profile/summary - Resumo para dashboard
# =====================================================================================
@router.get("/profile/summary")
async def get_profile_summary(
    authorization: str = Header(None),
    days: int = 30,
    supabase_service: Client = Depends(get_supabase_service),
    supabase_anon: Client = Depends(get_supabase_anon_auth_client),
):
    """
    Retorna resumo simples:
    - total_checkins_period
    - últimos check-ins (limit 5)
    - média por dia no período
    - role e flags básicas

    OBS: Não pretende substituir /stats admin, apenas facilitar dashboard pessoal.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou malformado")
    token = authorization.split(" ", 1)[1].strip()
    user_id = _extract_user_id(supabase_anon, token)

    profile = _get_profile(supabase_service, user_id)

    if days < 1 or days > 120:
        days = 30

    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_iso = since.isoformat()

    try:
        # Contagem e amostra
        ck_resp = supabase_service.table("check_ins") \
            .select("id,checkin_date,mood_data") \
            .eq("user_id", user_id) \
            .gte("checkin_date", since_iso) \
            .order("checkin_date", desc=True) \
            .limit(50) \
            .execute()

        checkins = ck_resp.data or []
        total_period = len(checkins)

        recent_sample = checkins[:5]
        days_div = days if days > 0 else 1
        avg_per_day = round(total_period / days_div, 2)

        return {
            "status": "success",
            "summary": {
                "user_id": user_id,
                "role": profile.get("role"),
                "is_test_patient": profile.get("is_test_patient"),
                "source": profile.get("source"),
                "period_days": days,
                "total_checkins_period": total_period,
                "avg_checkins_per_day": avg_per_day,
                "recent_checkins": recent_sample
            }
        }
    except APIError as e:
        logger.exception("[Account] Erro banco summary check_ins")
        raise HTTPException(status_code=500, detail=f"Erro banco (check_ins): {e}")
    except Exception as e:
        logger.exception("[Account] Erro inesperado summary")
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {e}")


# =====================================================================================
# GET /api/profile/health - Diagnóstico rápido
# =====================================================================================
@router.get("/profile/health")
async def profile_health():
    """
    Endpoint leve para ver se rota está viva.
    Pode ser usado pelo frontend para fallback rápido.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
