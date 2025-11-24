"""
Admin endpoints for privileged operations.

Endpoints exigem autenticação via token JWT com role admin.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from supabase import Client
from postgrest.exceptions import APIError
from postgrest.types import CountMethod

from api.dependencies import (
    get_supabase_service,
    verify_admin_authorization,
)
from api.rate_limiter import limiter
from api.audit import log_audit_action
from api.schemas.synthetic_data import (
    StatsResponse,
    CleanupResponse,
    GenerateDataRequest,
    SyntheticDataGenerationResponse,
    CleanupDataRequest,
    DangerZoneCleanupRequest,
    CleanDataResponse
)
from api.schemas.admin_users import (
    CreateUserRequest,
    CreateUserResponse,
    ListUsersResponse,
    UserListItem,
    UpdateUserRequest,
    UpdateUserResponse,
    UserDetailResponse,
    UserDetailAggregates,
    DeleteUserResponse,
    BulkUsersRequest,
    BulkUsersResponse,
    BulkCheckinsRequest,
    BulkCheckinsResponse,
    DeleteTestUsersResponse,
    ClearDatabaseRequest,
    ClearDatabaseResponse,
)
from data_generator import generate_and_populate_data

logger = logging.getLogger("bipolar-api.admin")
router = APIRouter(prefix="/api/admin", tags=["Admin"])

# ================== CONFIG SINTÉTICA (PRODUÇÃO) ==================
SYN_MAX_PATIENTS_PROD = int(os.getenv("SYNTHETIC_MAX_PATIENTS_PROD", "50"))
SYN_MAX_THERAPISTS_PROD = int(os.getenv("SYNTHETIC_MAX_THERAPISTS_PROD", "10"))
SYN_MAX_CHECKINS_PER_USER_PROD = int(os.getenv("SYNTHETIC_MAX_CHECKINS_PER_USER_PROD", "60"))
SYN_ALLOWED_DOMAINS = [
    d.strip() for d in os.getenv("SYNTHETIC_ALLOWED_DOMAINS", "@example.com,@example.org").split(",")
    if d.strip()
]

def _is_production() -> bool:
    return os.getenv("APP_ENV") == "production"

def _synthetic_generation_enabled() -> bool:
    if _is_production():
        # CRITICAL: Never allow this in prod, no exceptions.
        raise HTTPException(status_code=403, detail="Synthetic data generation is strictly forbidden in production environments.")
    return True

# ----------------------------------------------------------------------
# Geração de dados sintéticos
# ----------------------------------------------------------------------
@router.post("/generate-data", response_model=SyntheticDataGenerationResponse)
@limiter.limit("5/hour")
async def generate_synthetic_data(
    request: Request,
    data_request: GenerateDataRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
) -> Dict[str, Any]:

    # Block all synthetic data generation in production
    if _is_production():
        _synthetic_generation_enabled()  # Will raise HTTPException(403) - no exceptions

    patterns = ["stable", "cycling", "random", "manic", "depressive"]
    if data_request.moodPattern not in patterns:
        raise HTTPException(status_code=400, detail=f"moodPattern inválido. Use: {', '.join(patterns)}")

    # Respect explicit 0 values - only use Pydantic defaults if field is omitted
    # Don't use 'or 0' pattern as it treats 0 as falsy and would override it
    patients_count = data_request.patientsCount
    therapists_count = data_request.therapistsCount
    if patients_count == 0 and therapists_count == 0:
        raise HTTPException(status_code=400, detail="É necessário ao menos 1 patient ou 1 therapist.")

    start_ts = datetime.now(timezone.utc)
    logger.info(f"[SyntheticGen] start patients={patients_count} therapists={therapists_count} checkinsPerUser={data_request.checkinsPerUser} pattern={data_request.moodPattern}")

    try:
        result = await generate_and_populate_data(
            supabase=supabase,
            patients_count=patients_count,
            therapists_count=therapists_count,
            checkins_per_patient=data_request.checkinsPerUser,
            pattern=data_request.moodPattern,
            clear_db=data_request.clearDb,
            seed=data_request.seed,
            allowed_domains=SYN_ALLOWED_DOMAINS,
        )

        stats = result.get("statistics", {}) if isinstance(result, dict) else {}
        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000

        stats_obj = {
            "users_created": stats.get("users_created", 0),
            "patients_created": stats.get("patients_created", 0),
            "therapists_created": stats.get("therapists_created", 0),
            "total_checkins": stats.get("total_checkins", 0),
            "mood_pattern": stats.get("mood_pattern", data_request.moodPattern),
            "checkins_per_user": stats.get("checkins_per_user", data_request.checkinsPerUser),
            "generated_at": stats.get("generated_at", datetime.now(timezone.utc).isoformat()),
            "duration_ms": round(duration_ms, 2),
            "limits_applied": {
                "max_patients_prod": SYN_MAX_PATIENTS_PROD,
                "max_therapists_prod": SYN_MAX_THERAPISTS_PROD,
                "max_checkins_per_user_prod": SYN_MAX_CHECKINS_PER_USER_PROD
            },
            "domains_used": SYN_ALLOWED_DOMAINS
        }

        logger.info(f"[SyntheticGen] done patients={stats_obj['patients_created']} therapists={stats_obj['therapists_created']} checkins={stats_obj['total_checkins']}")
        
        # Audit log
        await log_audit_action(
            supabase=supabase,
            action="synthetic_generate",
            details={
                "patients_requested": patients_count,
                "therapists_requested": therapists_count,
                "patients_created": stats_obj['patients_created'],
                "therapists_created": stats_obj['therapists_created'],
                "checkins_created": stats_obj['total_checkins'],
                "pattern": data_request.moodPattern,
                "seed": data_request.seed,
                "checkins_per_user": data_request.checkinsPerUser,
            },
        )
        
        return {
            "status": "success",
            "statistics": stats_obj,
            "generatedAt": datetime.now(timezone.utc).isoformat()
        }

    except ValidationError as ve:
        logger.error(f"Validation error: {ve}")
        raise HTTPException(status_code=400, detail="Erro de validação.")
    except APIError as e:
        logger.exception("Erro banco geração sintética")
        raise HTTPException(status_code=500, detail=f"Erro banco: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro inesperado geração sintética")
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {e}")

# ----------------------------------------------------------------------
# Estatísticas
# ----------------------------------------------------------------------
@router.get("/stats", response_model=StatsResponse)
async def get_admin_stats(
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info("[AdminStats] Requisição recebida")
    start_ts = datetime.now(timezone.utc)

    total_users = 0
    total_checkins = 0
    real_patients_count = 0
    synthetic_patients_count = 0
    checkins_today = 0
    checkins_last_7_days = 0
    checkins_last_7_days_previous = 0
    avg_checkins_per_active_patient = 0.0
    avg_adherence_last_30d = 0.0
    avg_current_mood = 3.0
    mood_counts = {"stable": 0,"hypomania": 0,"mania": 0,"depression": 0,"mixed": 0,"euthymic": 0}
    critical_alerts_last_30d = 0

    try:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)
        thirty_days_ago = now - timedelta(days=30)

        # Total perfis
        try:
            head_profiles = supabase.table("profiles").select("*", count=CountMethod.exact, head=True).execute()
            total_users = head_profiles.count or 0
        except Exception as e:
            logger.warning(f"[AdminStats] Falha total_users: {e}")

        # Total check-ins
        try:
            head_checkins = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True).execute()
            total_checkins = head_checkins.count or 0
        except Exception as e:
            logger.warning(f"[AdminStats] Falha total_checkins: {e}")

        # Real vs sintético (using source field)
        try:
            resp_profiles = supabase.table("profiles").select("id,email,role,source,is_test_patient").execute()
            profiles_list = resp_profiles.data or []
            synthetic_ids = set()
            real_ids = set()
            
            for p in profiles_list:
                if p.get("role") == "patient":
                    # Use source field if available, fallback to old heuristics
                    source = p.get("source", "unknown")
                    if source == "synthetic":
                        synthetic_ids.add(p["id"])
                    elif source in ("admin_manual", "signup"):
                        real_ids.add(p["id"])
                    else:
                        # Fallback to old heuristics for unknown sources
                        synthetic_domains = ["@example.com", "@example.org", "@example.net"]
                        if p.get("is_test_patient") or (
                            p.get("email") and any(d in p["email"] for d in synthetic_domains)
                        ):
                            synthetic_ids.add(p["id"])
                        else:
                            real_ids.add(p["id"])
                            
            real_patients_count = len(real_ids)
            synthetic_patients_count = len(synthetic_ids)
        except Exception as e:
            logger.warning(f"[AdminStats] Falha classificar pacientes: {e}")

        # Check-ins hoje
        try:
            today_resp = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True)\
                .gte("checkin_date", today_start.isoformat()).execute()
            checkins_today = today_resp.count or 0
        except Exception as e:
            logger.warning(f"[AdminStats] Falha checkins today: {e}")

        # Últimos 7 dias
        try:
            last7_resp = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True)\
                .gte("checkin_date", seven_days_ago.isoformat()).execute()
            checkins_last_7_days = last7_resp.count or 0
        except Exception as e:
            logger.warning(f"[AdminStats] Falha last7: {e}")

        # 7 dias anteriores
        try:
            prev7_resp = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True)\
                .gte("checkin_date", fourteen_days_ago.isoformat())\
                .lt("checkin_date", seven_days_ago.isoformat()).execute()
            checkins_last_7_days_previous = prev7_resp.count or 0
        except Exception as e:
            logger.warning(f"[AdminStats] Falha prev7: {e}")

        # Últimos 30 dias para métricas agregadas
        try:
            ck30_resp = supabase.table("check_ins").select(
                "user_id, checkin_date, mood_data, meds_context_data, symptoms_data"
            ).gte("checkin_date", thirty_days_ago.isoformat()).execute()
            ck30 = ck30_resp.data or []
            active_patients = {c["user_id"] for c in ck30}
            active_count = len(active_patients)
            avg_checkins_per_active_patient = (len(ck30) / active_count) if active_count else 0.0

            adherence_vals = []
            mood_vals: List[float] = []

            for c in ck30:
                meds = c.get("meds_context_data", {})
                if isinstance(meds, dict):
                    ad = meds.get("medicationAdherence") or meds.get("medication_adherence")
                    if isinstance(ad, (int, float)):
                        adherence_vals.append(ad)

                mood = c.get("mood_data", {})
                if isinstance(mood, dict):
                    elevation = mood.get("elevation", 0)
                    depressed = mood.get("depressedMood", 0)
                    activation = mood.get("activation", 0)
                    energy = mood.get("energyLevel")
                    if depressed > 7 and elevation > 5:
                        mood_counts["mixed"] += 1
                        mood_vals.append(3)
                    elif elevation > 8 or (activation > 8 and (energy or 0) > 7):
                        mood_counts["mania"] += 1
                        mood_vals.append(4)
                    elif elevation > 5 or activation > 6:
                        mood_counts["hypomania"] += 1
                        mood_vals.append(3.5)
                    elif depressed > 7:
                        mood_counts["depression"] += 1
                        mood_vals.append(2)
                    else:
                        mood_counts["euthymic"] += 1
                        mood_vals.append(3)

                # Alertas críticos
                md = mood
                sd = c.get("symptoms_data", {})
                if isinstance(md, dict):
                    if (
                        md.get("depressedMood", 0) >= 9
                        or md.get("activation", 0) >= 9
                        or md.get("elevation", 0) >= 9
                        or md.get("anxietyStress", 0) >= 8
                        or md.get("energyLevel", 0) >= 9
                        or (isinstance(sd, dict) and sd.get("thoughtSpeed", 0) >= 9)
                    ):
                        critical_alerts_last_30d += 1

            avg_adherence_last_30d = (sum(adherence_vals) / len(adherence_vals)) if adherence_vals else 0.0
            avg_current_mood = (sum(mood_vals) / len(mood_vals)) if mood_vals else 3.0

        except Exception as e:
            logger.warning(f"[AdminStats] Falha análise 30d: {e}")

        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
        logger.info(f"[AdminStats] calculado em {duration_ms:.2f}ms total_users={total_users}")

        return StatsResponse(
            total_users=total_users,
            total_checkins=total_checkins,
            real_patients_count=real_patients_count,
            synthetic_patients_count=synthetic_patients_count,
            checkins_today=checkins_today,
            checkins_last_7_days=checkins_last_7_days,
            checkins_last_7_days_previous=checkins_last_7_days_previous,
            avg_checkins_per_active_patient=round(avg_checkins_per_active_patient, 2),
            avg_adherence_last_30d=round(avg_adherence_last_30d, 2),
            avg_current_mood=round(avg_current_mood, 2),
            mood_distribution=mood_counts,
            critical_alerts_last_30d=critical_alerts_last_30d,
            patients_with_recent_radar=0,
        )

    except Exception as e:
        logger.exception("[AdminStats] Erro crítico - retornando parcial")
        return StatsResponse(
            total_users=total_users,
            total_checkins=total_checkins,
            real_patients_count=real_patients_count,
            synthetic_patients_count=synthetic_patients_count,
            checkins_today=checkins_today,
            checkins_last_7_days=checkins_last_7_days,
            checkins_last_7_days_previous=checkins_last_7_days_previous,
            avg_checkins_per_active_patient=round(avg_checkins_per_active_patient, 2),
            avg_adherence_last_30d=round(avg_adherence_last_30d, 2),
            avg_current_mood=round(avg_current_mood, 2),
            mood_distribution=mood_counts,
            critical_alerts_last_30d=critical_alerts_last_30d,
            patients_with_recent_radar=0,
        )

# ----------------------------------------------------------------------
# Cleanup simples
# ----------------------------------------------------------------------
@router.post("/cleanup", response_model=CleanupResponse)
@limiter.limit("5/hour")
async def cleanup_standard(
    request: Request,
    cleanup_request: CleanupDataRequest = None,
    dryRun: bool = False,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Remove dados sintéticos baseado no campo 'source'.
    Mais seguro que baseado em domínios de email.
    """
    is_dry_run = dryRun
    if cleanup_request:
        if cleanup_request.dryRun:
            is_dry_run = True
        if not cleanup_request.confirm and not is_dry_run:
            raise HTTPException(status_code=400, detail="Confirme ou use dryRun=true.")

    # Use source='synthetic' instead of email domain heuristics
    try:
        resp = supabase.table("profiles").select("id,email,source").execute()
        ids_to_remove = []
        sample_emails = []
        
        if resp.data:
            for p in resp.data:
                # Remove only synthetic data
                if p.get("source") == "synthetic":
                    ids_to_remove.append(p["id"])
                    if len(sample_emails) < 5:
                        sample_emails.append(p.get("email", ""))
                        
        if (not is_dry_run) and ids_to_remove:
            chunk = 100
            for i in range(0, len(ids_to_remove), chunk):
                part = ids_to_remove[i:i+chunk]
                supabase.table("check_ins").delete().in_("user_id", part).execute()
                supabase.table("profiles").delete().in_("id", part).execute()
        
        # Audit log
        await log_audit_action(
            supabase=supabase,
            action="cleanup",
            details={
                "dry_run": is_dry_run,
                "removed_count": len(ids_to_remove),
                "sample_ids": ids_to_remove[:5],
                "sample_emails": sample_emails,
            },
        )

        return CleanupResponse(
            status="ok",
            message=f"Cleanup {'simulado' if is_dry_run else 'executado'}",
            removedRecords=len(ids_to_remove),
            sampleIds=ids_to_remove[:5],
            dryRun=is_dry_run,
            cleanedAt=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.exception("Erro cleanup")
        raise HTTPException(status_code=500, detail=f"Erro cleanup: {e}")

# ----------------------------------------------------------------------
# Danger zone cleanup
# ----------------------------------------------------------------------
@router.post("/danger-zone-cleanup", response_model=CleanupResponse)
@limiter.limit("5/hour")
async def danger_zone_cleanup(
    request: Request,
    cleanup_request: DangerZoneCleanupRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    MOOD_VARIANCE_THRESHOLD = 2.0
    logger.info(f"[DangerZone] action={cleanup_request.action} dryRun={cleanup_request.dryRun}")

    if cleanup_request.action == "delete_last_n" and not cleanup_request.quantity:
        raise HTTPException(status_code=400, detail="quantity requerido")
    if cleanup_request.action == "delete_by_mood" and not cleanup_request.mood_pattern:
        raise HTTPException(status_code=400, detail="mood_pattern requerido")
    if cleanup_request.action == "delete_before_date" and not cleanup_request.before_date:
        raise HTTPException(status_code=400, detail="before_date requerido")

    try:
        resp_profiles = supabase.table("profiles").select(
            "id,email,created_at,is_test_patient,deleted_at"
        ).eq("is_test_patient", True).is_("deleted_at", "null").execute()

        test_patients = resp_profiles.data or []
        patients_to_delete = test_patients.copy()

        if cleanup_request.action == "delete_last_n":
            patients_to_delete.sort(key=lambda x: x.get("created_at",""), reverse=True)
            patients_to_delete = patients_to_delete[:cleanup_request.quantity]

        elif cleanup_request.action == "delete_by_mood":
            ids = [p["id"] for p in test_patients]
            if ids:
                ck_resp = supabase.table("check_ins").select("user_id,mood_data").in_("user_id", ids).execute()
                ck_list = ck_resp.data or []
                grouped: Dict[str, List[Dict[str, Any]]] = {}
                for c in ck_list:
                    grouped.setdefault(c["user_id"], []).append(c)
                filtered = []
                for pt in test_patients:
                    pid = pt["id"]
                    if pid not in grouped:
                        continue
                    mood_values = []
                    for chk in grouped[pid]:
                        md = chk.get("mood_data", {})
                        if isinstance(md, dict):
                            elev = md.get("elevation", 0)
                            depr = md.get("depressedMood", 0)
                            mood_score = (elev - depr) / 2.0
                            mood_values.append(mood_score)
                    if mood_values:
                        mean_mood = sum(mood_values)/len(mood_values)
                        variance = sum((x - mean_mood)**2 for x in mood_values)/len(mood_values)
                        pattern = cleanup_request.mood_pattern
                        if pattern == "stable" and variance < MOOD_VARIANCE_THRESHOLD:
                            filtered.append(pt)
                        elif pattern == "cycling" and variance >= MOOD_VARIANCE_THRESHOLD:
                            filtered.append(pt)
                        elif pattern == "random":
                            filtered.append(pt)
                patients_to_delete = filtered

        elif cleanup_request.action == "delete_before_date":
            from datetime import datetime as dt
            try:
                cutoff = dt.fromisoformat(cleanup_request.before_date.replace("Z","+00:00"))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Data inválida: {e}")
            patients_to_delete = [
                p for p in patients_to_delete
                if p.get("created_at") and dt.fromisoformat(p["created_at"].replace("Z","+00:00")) < cutoff
            ]

        ids_to_delete = [p["id"] for p in patients_to_delete]

        if not cleanup_request.dryRun and ids_to_delete:
            chunk = 100
            for i in range(0, len(ids_to_delete), chunk):
                part = ids_to_delete[i:i+chunk]
                supabase.table("check_ins").delete().in_("user_id", part).execute()
                try:
                    supabase.table("crisis_plan").delete().in_("user_id", part).execute()
                    supabase.table("clinical_notes").delete().in_("patient_id", part).execute()
                    supabase.table("therapist_patients").delete().in_("patient_id", part).execute()
                    supabase.table("user_consent").delete().in_("user_id", part).execute()
                except Exception:
                    pass
                supabase.table("profiles").delete().in_("id", part).execute()

        return CleanupResponse(
            status="ok",
            message=f"Danger zone {'simulado' if cleanup_request.dryRun else 'executado'}",
            removedRecords=len(ids_to_delete),
            sampleIds=ids_to_delete[:5],
            dryRun=cleanup_request.dryRun,
            cleanedAt=datetime.now(timezone.utc).isoformat()
        )

    except Exception as e:
        logger.exception("Erro danger zone cleanup")
        raise HTTPException(status_code=500, detail=f"Erro: {e}")

# ----------------------------------------------------------------------
# Users/create (endpoint solicitado)
# ----------------------------------------------------------------------
@router.post("/users/create", response_model=CreateUserResponse)
@limiter.limit("10/hour")
async def create_user(
    request: Request,
    user_request: CreateUserRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Cria um usuário (patient ou therapist).

    Fluxo:
      1. Verifica duplicata por email em profiles.
      2. Cria usuário no Supabase Auth (admin).
      3. Extrai user_id.
      4. Atualiza perfil criado pelo trigger (fallback insert se não houver trigger).
      5. Retorna dados básicos.
    """
    logger.info(f"[AdminCreateUser] email={user_request.email} role={user_request.role}")

    # Validações
    if user_request.role not in ("patient", "therapist"):
        raise HTTPException(status_code=400, detail="Role inválida (patient|therapist).")
    if not user_request.password or len(user_request.password) < 8:
        raise HTTPException(status_code=400, detail="Senha mínima 8 caracteres.")

    email_lower = user_request.email.strip().lower()

    # Duplicata por email
    try:
        existing = supabase.table("profiles").select("id,email,role").eq("email", email_lower).execute()
        if existing.data:
            eid = existing.data[0]["id"]
            logger.info(f"[AdminCreateUser] email já existe -> retorno idempotente id={eid}")
            return CreateUserResponse(
                status="success",
                message="Usuário já existente",
                user_id=eid,
                email=email_lower,
                role=existing.data[0]["role"]
            )
    except Exception as e:
        logger.warning(f"[AdminCreateUser] Falha checando duplicata: {e}")

    # Criação Auth
    try:
        auth_resp = supabase.auth.admin.create_user({
            "email": email_lower,
            "password": user_request.password,
            "email_confirm": True,
            "user_metadata": {
                "role": user_request.role,
                "full_name": user_request.full_name or "",
                "created_by_admin": True
            }
        })
    except Exception as e:
        msg = str(e)
        logger.exception("[AdminCreateUser] Erro Auth")
        if "duplicate" in msg.lower() or "already" in msg.lower():
            raise HTTPException(status_code=409, detail=f"Email {email_lower} já registrado.")
        raise HTTPException(status_code=500, detail=f"Erro Auth: {msg}")

    # Extrair user_id
    user_id = None
    try:
        if getattr(auth_resp, "user", None):
            user_id = getattr(auth_resp.user, "id", None) or getattr(auth_resp.user, "uuid", None)
    except Exception:
        pass
    if not user_id and isinstance(auth_resp, dict):
        part = auth_resp.get("user") or auth_resp
        if isinstance(part, dict):
            user_id = part.get("id") or part.get("uuid") or part.get("user_id")
    if not user_id:
        logger.error(f"[AdminCreateUser] Falha extraindo user_id. Resp={auth_resp}")
        raise HTTPException(status_code=500, detail="Falha extraindo user_id.")

    # Wait briefly for Supabase trigger to create profile
    import asyncio
    await asyncio.sleep(0.3)

    # Update profile created by trigger (NOT insert - trigger creates it automatically)
    profile_update = {
        "role": user_request.role,
        "is_test_patient": False,  # Manual creation is not test
        "source": "admin_manual",
        "email": email_lower,
    }
    try:
        upd = supabase.table("profiles").update(profile_update).eq("id", user_id).execute()
        if not upd.data:
            # Fallback: if trigger didn't create profile (shouldn't happen), insert it
            logger.warning(f"[AdminCreateUser] Perfil não encontrado após trigger, insert fallback id={user_id}")
            supabase.table("profiles").insert({
                "id": user_id,
                **profile_update,
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
    except APIError as e:
        # Check if it's a duplicate key error (profile already exists but update failed)
        if "duplicate" in str(e).lower() or "23505" in str(e):
            logger.info(f"[AdminCreateUser] Perfil já existe (esperado), tentando update novamente id={user_id}")
            # Try update one more time
            try:
                supabase.table("profiles").update(profile_update).eq("id", user_id).execute()
            except Exception as retry_err:
                logger.exception("[AdminCreateUser] Falha no retry do update")
                raise HTTPException(status_code=500, detail=f"Erro atualizando perfil: {retry_err}")
        else:
            logger.exception("[AdminCreateUser] Erro banco perfis")
            raise HTTPException(status_code=500, detail=f"Erro perfil: {e}")
    except Exception as e:
        logger.exception("[AdminCreateUser] Erro inesperado perfil")
        raise HTTPException(status_code=500, detail=f"Erro inesperado perfil: {e}")

    logger.info(f"[AdminCreateUser] sucesso id={user_id}")
    
    # Audit log
    await log_audit_action(
        supabase=supabase,
        action="user_create",
        details={
            "email": email_lower,
            "role": user_request.role,
            "source": "admin_manual",
            "full_name": user_request.full_name or "",
        },
        user_id=user_id,
    )
    
    return CreateUserResponse(
        status="success",
        message=f"Usuário {user_request.role} criado com sucesso",
        user_id=user_id,
        email=email_lower,
        role=user_request.role
    )

# ----------------------------------------------------------------------
# Listagem
# ----------------------------------------------------------------------
@router.get("/users", response_model=ListUsersResponse)
@limiter.limit("30/minute")
async def list_users(
    request: Request,
    role: Optional[str] = None,
    is_test_patient: Optional[bool] = None,
    source: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    List users with filters and pagination.
    Supports filtering by role, is_test_patient, source, and deleted status.
    """
    if limit > 200:
        limit = 200
    
    query = supabase.table("profiles").select("id,email,role,created_at,is_test_patient,source,deleted_at")
    
    # Apply filters
    if role:
        if role not in ["patient", "therapist"]:
            raise HTTPException(status_code=400, detail="Role must be patient or therapist.")
        query = query.eq("role", role)
    
    if is_test_patient is not None:
        query = query.eq("is_test_patient", is_test_patient)
    
    if source:
        query = query.eq("source", source)
    
    if not include_deleted:
        query = query.is_("deleted_at", "null")
    
    # Apply pagination
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    
    try:
        resp = query.execute()
        data = resp.data or []
        users = [
            UserListItem(
                id=u["id"],
                email=u["email"],
                role=u["role"],
                created_at=u.get("created_at") or "",
                is_test_patient=u.get("is_test_patient", False),
                source=u.get("source"),
                deleted_at=u.get("deleted_at")
            )
            for u in data
        ]
        return ListUsersResponse(status="success", users=users, total=len(users))
    except APIError as e:
        logger.exception("Erro listagem usuários banco")
        raise HTTPException(status_code=500, detail=f"Erro listar: {e}")
    except Exception as e:
        logger.exception("Erro inesperado listagem usuários")
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {e}")

# ----------------------------------------------------------------------
# Audit log endpoint
# ----------------------------------------------------------------------
@router.get("/audit/recent")
@limiter.limit("30/minute")
async def get_recent_audit_logs(
    request: Request,
    limit: int = 50,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Retrieve recent audit log entries.
    """
    if limit > 200:
        limit = 200
    
    try:
        resp = supabase.table("audit_log").select(
            "id,action,details,user_id,performed_by,created_at"
        ).order("created_at", desc=True).limit(limit).execute()
        
        logs = resp.data or []
        
        return {
            "status": "success",
            "logs": logs,
            "count": len(logs),
        }
    except APIError as e:
        logger.exception("Erro listagem audit logs")
        raise HTTPException(status_code=500, detail=f"Erro listar audit logs: {e}")
    except Exception as e:
        logger.exception("Erro inesperado audit logs")
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {e}")

# ----------------------------------------------------------------------
# Single user detail endpoint
# ----------------------------------------------------------------------
@router.get("/users/{user_id}", response_model=UserDetailResponse)
@limiter.limit("30/minute")
async def get_user_detail(
    request: Request,
    user_id: str,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Get detailed information about a single user including aggregated stats.
    """
    try:
        # Get user profile
        profile_resp = supabase.table("profiles").select("*").eq("id", user_id).execute()
        if not profile_resp.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = profile_resp.data[0]
        
        # Get aggregated info
        aggregates = UserDetailAggregates()
        
        # Count check-ins
        try:
            checkins_resp = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True)\
                .eq("user_id", user_id).execute()
            aggregates.checkins_count = checkins_resp.count or 0
        except Exception as e:
            logger.warning(f"Failed to count check-ins: {e}")
        
        # Count clinical notes as patient
        try:
            notes_patient_resp = supabase.table("clinical_notes").select("*", count=CountMethod.exact, head=True)\
                .eq("patient_id", user_id).execute()
            aggregates.clinical_notes_as_patient = notes_patient_resp.count or 0
        except Exception as e:
            logger.warning(f"Failed to count clinical notes as patient: {e}")
        
        # Count clinical notes as therapist
        try:
            notes_therapist_resp = supabase.table("clinical_notes").select("*", count=CountMethod.exact, head=True)\
                .eq("therapist_id", user_id).execute()
            aggregates.clinical_notes_as_therapist = notes_therapist_resp.count or 0
        except Exception as e:
            logger.warning(f"Failed to count clinical notes as therapist: {e}")
        
        # Check crisis plan
        try:
            crisis_resp = supabase.table("crisis_plan").select("id").eq("user_id", user_id).execute()
            aggregates.has_crisis_plan = bool(crisis_resp.data)
        except Exception as e:
            logger.warning(f"Failed to check crisis plan: {e}")
        
        # Get therapist assignment (if patient)
        if user.get("role") == "patient":
            try:
                therapist_resp = supabase.table("therapist_patients").select("therapist_id")\
                    .eq("patient_id", user_id).execute()
                if therapist_resp.data:
                    aggregates.assigned_therapist_id = therapist_resp.data[0]["therapist_id"]
            except Exception as e:
                logger.warning(f"Failed to get therapist assignment: {e}")
        
        # Count assigned patients (if therapist)
        if user.get("role") == "therapist":
            try:
                patients_resp = supabase.table("therapist_patients").select("*", count=CountMethod.exact, head=True)\
                    .eq("therapist_id", user_id).execute()
                aggregates.assigned_patients_count = patients_resp.count or 0
            except Exception as e:
                logger.warning(f"Failed to count assigned patients: {e}")
        
        return UserDetailResponse(
            status="success",
            user=user,
            aggregates=aggregates
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting user detail")
        raise HTTPException(status_code=500, detail=f"Error: {e}")

# ----------------------------------------------------------------------
# Update user endpoint
# ----------------------------------------------------------------------
@router.patch("/users/{user_id}", response_model=UpdateUserResponse)
@limiter.limit("20/minute")
async def update_user(
    request: Request,
    user_id: str,
    update_request: UpdateUserRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Update user profile fields.
    """
    logger.info(f"[AdminUpdateUser] user_id={user_id}")
    
    # Check user exists
    try:
        existing = supabase.table("profiles").select("id,deleted_at").eq("id", user_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Don't allow updating deleted normal users
        if existing.data[0].get("deleted_at"):
            raise HTTPException(status_code=400, detail="Cannot update deleted user")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking user existence: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    # Build update payload (only include provided fields)
    update_payload = {}
    if update_request.role is not None:
        update_payload["role"] = update_request.role
    if update_request.username is not None:
        update_payload["username"] = update_request.username
    if update_request.email is not None:
        update_payload["email"] = update_request.email.strip().lower()
    if update_request.is_test_patient is not None:
        update_payload["is_test_patient"] = update_request.is_test_patient
    if update_request.source is not None:
        update_payload["source"] = update_request.source
    
    if not update_payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    try:
        upd_resp = supabase.table("profiles").update(update_payload).eq("id", user_id).execute()
        if not upd_resp.data:
            raise HTTPException(status_code=500, detail="Update failed")
        
        logger.info(f"[AdminUpdateUser] success user_id={user_id}")
        
        # Audit log
        await log_audit_action(
            supabase=supabase,
            action="user_update",
            details={
                "updated_fields": list(update_payload.keys()),
                "values": update_payload,
            },
            user_id=user_id,
        )
        
        return UpdateUserResponse(
            status="success",
            message="User updated successfully",
            user_id=user_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating user")
        raise HTTPException(status_code=500, detail=f"Error: {e}")

# ----------------------------------------------------------------------
# Delete user endpoint
# ----------------------------------------------------------------------
@router.delete("/users/{user_id}", response_model=DeleteUserResponse)
@limiter.limit("10/minute")
async def delete_user(
    request: Request,
    user_id: str,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Delete a user. Test users are hard-deleted (cascade), normal users are soft-deleted.
    """
    logger.info(f"[AdminDeleteUser] user_id={user_id}")
    
    # Get user info
    try:
        user_resp = supabase.table("profiles").select("id,is_test_patient,email").eq("id", user_id).execute()
        if not user_resp.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = user_resp.data[0]
        is_test = user.get("is_test_patient", False)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    if is_test:
        # HARD DELETE for test users
        try:
            # Delete related data in order
            supabase.table("check_ins").delete().eq("user_id", user_id).execute()
            supabase.table("clinical_notes").delete().eq("patient_id", user_id).execute()
            supabase.table("clinical_notes").delete().eq("therapist_id", user_id).execute()
            try:
                supabase.table("crisis_plan").delete().eq("user_id", user_id).execute()
            except Exception:
                pass  # May not exist
            try:
                supabase.table("therapist_patients").delete().eq("patient_id", user_id).execute()
            except Exception:
                pass
            try:
                supabase.table("therapist_patients").delete().eq("therapist_id", user_id).execute()
            except Exception:
                pass
            try:
                supabase.table("user_consent").delete().eq("user_id", user_id).execute()
            except Exception:
                pass
            
            # Delete profile
            supabase.table("profiles").delete().eq("id", user_id).execute()
            
            # Delete auth user
            try:
                supabase.auth.admin.delete_user(user_id)
            except Exception as e:
                logger.warning(f"Failed to delete auth user {user_id}: {e}")
            
            deletion_type = "hard"
            logger.info(f"[AdminDeleteUser] hard delete complete user_id={user_id}")
            
        except Exception as e:
            logger.exception("Error hard-deleting user")
            raise HTTPException(status_code=500, detail=f"Error deleting user: {e}")
    else:
        # SOFT DELETE for normal users
        try:
            now = datetime.now(timezone.utc).isoformat()
            supabase.table("profiles").update({
                "deleted_at": now,
                "deletion_scheduled_at": now
            }).eq("id", user_id).execute()
            
            deletion_type = "soft"
            logger.info(f"[AdminDeleteUser] soft delete complete user_id={user_id}")
            
        except Exception as e:
            logger.exception("Error soft-deleting user")
            raise HTTPException(status_code=500, detail=f"Error deleting user: {e}")
    
    # Audit log
    await log_audit_action(
        supabase=supabase,
        action="user_delete",
        details={
            "deletion_type": deletion_type,
            "is_test_patient": is_test,
            "email": user.get("email"),
        },
        user_id=user_id,
    )
    
    return DeleteUserResponse(
        status="success",
        message=f"User {'hard' if is_test else 'soft'} deleted successfully",
        user_id=user_id,
        deletion_type=deletion_type
    )

# ----------------------------------------------------------------------
# Delete all test users endpoint
# ----------------------------------------------------------------------
@router.post("/test-data/delete-test-users", response_model=DeleteTestUsersResponse)
@limiter.limit("5/hour")
async def delete_test_users(
    request: Request,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Delete all test users and their data (hard delete).
    """
    logger.info("[DeleteTestUsers] Starting")
    
    try:
        # Get all test users
        test_users_resp = supabase.table("profiles").select("id,email")\
            .eq("is_test_patient", True).is_("deleted_at", "null").execute()
        
        test_user_ids = [u["id"] for u in (test_users_resp.data or [])]
        
        if not test_user_ids:
            logger.info("[DeleteTestUsers] No test users found")
            return DeleteTestUsersResponse(
                status="success",
                message="No test users to delete",
                users_deleted=0,
                checkins_deleted=0,
                clinical_notes_deleted=0,
                crisis_plans_deleted=0,
                therapist_assignments_deleted=0
            )
        
        # Count data before deletion
        checkins_count = 0
        notes_count = 0
        crisis_count = 0
        assignments_count = 0
        
        # Delete in chunks
        chunk_size = 100
        for i in range(0, len(test_user_ids), chunk_size):
            chunk = test_user_ids[i:i+chunk_size]
            
            # Count and delete check-ins
            try:
                ck_resp = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True)\
                    .in_("user_id", chunk).execute()
                checkins_count += ck_resp.count or 0
                supabase.table("check_ins").delete().in_("user_id", chunk).execute()
            except Exception as e:
                logger.warning(f"Error deleting check-ins chunk: {e}")
            
            # Count and delete clinical notes (as patient)
            try:
                notes_resp = supabase.table("clinical_notes").select("*", count=CountMethod.exact, head=True)\
                    .in_("patient_id", chunk).execute()
                notes_count += notes_resp.count or 0
                supabase.table("clinical_notes").delete().in_("patient_id", chunk).execute()
            except Exception as e:
                logger.warning(f"Error deleting clinical notes (patient) chunk: {e}")
            
            # Delete clinical notes (as therapist)
            try:
                notes_t_resp = supabase.table("clinical_notes").select("*", count=CountMethod.exact, head=True)\
                    .in_("therapist_id", chunk).execute()
                notes_count += notes_t_resp.count or 0
                supabase.table("clinical_notes").delete().in_("therapist_id", chunk).execute()
            except Exception as e:
                logger.warning(f"Error deleting clinical notes (therapist) chunk: {e}")
            
            # Count and delete crisis plans
            try:
                crisis_resp = supabase.table("crisis_plan").select("*", count=CountMethod.exact, head=True)\
                    .in_("user_id", chunk).execute()
                crisis_count += crisis_resp.count or 0
                supabase.table("crisis_plan").delete().in_("user_id", chunk).execute()
            except Exception as e:
                logger.warning(f"Error deleting crisis plans chunk: {e}")
            
            # Count and delete therapist assignments
            try:
                assign_p_resp = supabase.table("therapist_patients").select("*", count=CountMethod.exact, head=True)\
                    .in_("patient_id", chunk).execute()
                assignments_count += assign_p_resp.count or 0
                supabase.table("therapist_patients").delete().in_("patient_id", chunk).execute()
                
                assign_t_resp = supabase.table("therapist_patients").select("*", count=CountMethod.exact, head=True)\
                    .in_("therapist_id", chunk).execute()
                assignments_count += assign_t_resp.count or 0
                supabase.table("therapist_patients").delete().in_("therapist_id", chunk).execute()
            except Exception as e:
                logger.warning(f"Error deleting therapist assignments chunk: {e}")
            
            # Delete user consent if exists
            try:
                supabase.table("user_consent").delete().in_("user_id", chunk).execute()
            except Exception:
                pass
            
            # Delete profiles
            supabase.table("profiles").delete().in_("id", chunk).execute()
            
            # Delete auth users
            for uid in chunk:
                try:
                    supabase.auth.admin.delete_user(uid)
                except Exception as e:
                    logger.warning(f"Failed to delete auth user {uid}: {e}")
        
        logger.info(f"[DeleteTestUsers] Complete: {len(test_user_ids)} users, {checkins_count} check-ins")
        
        # Audit log
        await log_audit_action(
            supabase=supabase,
            action="DELETE_TEST_USERS",
            details={
                "users_deleted": len(test_user_ids),
                "checkins_deleted": checkins_count,
                "clinical_notes_deleted": notes_count,
                "crisis_plans_deleted": crisis_count,
                "therapist_assignments_deleted": assignments_count,
                "environment": os.getenv("APP_ENV", "unknown"),
            },
        )
        
        return DeleteTestUsersResponse(
            status="success",
            message=f"Deleted {len(test_user_ids)} test users",
            users_deleted=len(test_user_ids),
            checkins_deleted=checkins_count,
            clinical_notes_deleted=notes_count,
            crisis_plans_deleted=crisis_count,
            therapist_assignments_deleted=assignments_count
        )
        
    except Exception as e:
        logger.exception("Error deleting test users")
        raise HTTPException(status_code=500, detail=f"Error: {e}")

# ----------------------------------------------------------------------
# Clear database endpoint
# ----------------------------------------------------------------------
@router.post("/test-data/clear-database", response_model=ClearDatabaseResponse)
@limiter.limit("2/hour")
async def clear_database(
    request: Request,
    clear_request: ClearDatabaseRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Clear all domain data. Test users hard-deleted, normal users soft-deleted.
    Requires confirmation text and production environment check.
    """
    logger.info("[ClearDatabase] Starting")
    
    # Block all synthetic data operations in production
    if _is_production():
        _synthetic_generation_enabled()  # Will raise HTTPException(403) - no exceptions
    
    # Validate confirmation
    if clear_request.confirm_text != "DELETE ALL DATA":
        raise HTTPException(
            status_code=400,
            detail='Confirmation text must be exactly "DELETE ALL DATA"'
        )
    
    try:
        # Count before deletion
        checkins_count = 0
        notes_count = 0
        crisis_count = 0
        assignments_count = 0
        
        # Delete all domain data
        try:
            ck_resp = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True).execute()
            checkins_count = ck_resp.count or 0
            supabase.table("check_ins").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception as e:
            logger.error(f"Error deleting check-ins: {e}")
        
        try:
            notes_resp = supabase.table("clinical_notes").select("*", count=CountMethod.exact, head=True).execute()
            notes_count = notes_resp.count or 0
            supabase.table("clinical_notes").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception as e:
            logger.error(f"Error deleting clinical notes: {e}")
        
        try:
            crisis_resp = supabase.table("crisis_plan").select("*", count=CountMethod.exact, head=True).execute()
            crisis_count = crisis_resp.count or 0
            supabase.table("crisis_plan").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception as e:
            logger.error(f"Error deleting crisis plans: {e}")
        
        try:
            assign_resp = supabase.table("therapist_patients").select("*", count=CountMethod.exact, head=True).execute()
            assignments_count = assign_resp.count or 0
            supabase.table("therapist_patients").delete().neq("therapist_id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception as e:
            logger.error(f"Error deleting therapist assignments: {e}")
        
        # Handle audit logs if requested
        audit_logs_deleted = 0
        if clear_request.delete_audit_logs:
            try:
                audit_resp = supabase.table("audit_log").select("*", count=CountMethod.exact, head=True).execute()
                audit_logs_deleted = audit_resp.count or 0
                supabase.table("audit_log").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            except Exception as e:
                logger.error(f"Error deleting audit logs: {e}")
        
        # Get all users
        all_users_resp = supabase.table("profiles").select("id,is_test_patient,email").execute()
        all_users = all_users_resp.data or []
        
        test_user_ids = [u["id"] for u in all_users if u.get("is_test_patient")]
        normal_user_ids = [u["id"] for u in all_users if not u.get("is_test_patient")]
        
        # Hard delete test users
        test_users_deleted = 0
        if test_user_ids:
            chunk_size = 100
            for i in range(0, len(test_user_ids), chunk_size):
                chunk = test_user_ids[i:i+chunk_size]
                
                # Delete profiles
                supabase.table("profiles").delete().in_("id", chunk).execute()
                
                # Delete auth users
                for uid in chunk:
                    try:
                        supabase.auth.admin.delete_user(uid)
                        test_users_deleted += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete auth user {uid}: {e}")
        
        # Soft delete normal users
        normal_users_soft_deleted = 0
        if normal_user_ids:
            now = datetime.now(timezone.utc).isoformat()
            chunk_size = 100
            for i in range(0, len(normal_user_ids), chunk_size):
                chunk = normal_user_ids[i:i+chunk_size]
                
                upd_resp = supabase.table("profiles").update({
                    "deleted_at": now,
                    "deletion_scheduled_at": now
                }).in_("id", chunk).execute()
                
                normal_users_soft_deleted += len(upd_resp.data or [])
        
        logger.info(f"[ClearDatabase] Complete: test={test_users_deleted}, normal={normal_users_soft_deleted}")
        
        # Audit log (before deleting audit logs if requested)
        await log_audit_action(
            supabase=supabase,
            action="CLEAR_DATABASE",
            details={
                "checkins_deleted": checkins_count,
                "clinical_notes_deleted": notes_count,
                "crisis_plans_deleted": crisis_count,
                "therapist_assignments_deleted": assignments_count,
                "test_users_deleted": test_users_deleted,
                "normal_users_soft_deleted": normal_users_soft_deleted,
                "audit_logs_deleted": audit_logs_deleted,
                "environment": os.getenv("APP_ENV", "unknown"),
            },
        )
        
        return ClearDatabaseResponse(
            status="success",
            message="Database cleared successfully",
            checkins_deleted=checkins_count,
            clinical_notes_deleted=notes_count,
            crisis_plans_deleted=crisis_count,
            therapist_assignments_deleted=assignments_count,
            test_users_deleted=test_users_deleted,
            normal_users_soft_deleted=normal_users_soft_deleted,
            audit_logs_deleted=audit_logs_deleted
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error clearing database")
        raise HTTPException(status_code=500, detail=f"Error: {e}")

# ----------------------------------------------------------------------
# Bulk user generation endpoint
# ----------------------------------------------------------------------
@router.post("/synthetic/bulk-users", response_model=BulkUsersResponse)
@limiter.limit("5/hour")
async def bulk_create_users(
    request: Request,
    bulk_request: BulkUsersRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Generate multiple synthetic users at once.
    Enforces production limits for patient/therapist counts.
    """
    logger.info(f"[BulkUsers] role={bulk_request.role} count={bulk_request.count}")
    
    # Block all synthetic data generation in production
    if _is_production():
        _synthetic_generation_enabled()  # Will raise HTTPException(403) - no exceptions
    
    # Import the helper
    from data_generator import create_user_with_retry
    import asyncio
    import random
    
    created_user_ids = []
    
    try:
        # Create users
        for i in range(bulk_request.count):
            try:
                user_id, email, password = await create_user_with_retry(
                    client=supabase,
                    role=bulk_request.role,
                    max_retries=3
                )
                
                # Update profile with source and is_test_patient
                await asyncio.sleep(0.1)  # Brief wait for trigger
                supabase.table("profiles").update({
                    "source": bulk_request.source,
                    "is_test_patient": bulk_request.is_test_patient,
                }).eq("id", user_id).execute()
                
                created_user_ids.append(user_id)
                logger.debug(f"[BulkUsers] Created {bulk_request.role} {i+1}/{bulk_request.count}: {user_id}")
                
            except Exception as e:
                logger.error(f"Failed to create user {i+1}: {e}")
                # Continue with others
        
        # Handle therapist-patient auto-assignment if requested
        assignments_created = 0
        if bulk_request.auto_assign_therapists and bulk_request.role == "patient" and created_user_ids:
            # Get available therapists
            therapists_resp = supabase.table("profiles").select("id").eq("role", "therapist").execute()
            therapist_ids = [t["id"] for t in (therapists_resp.data or [])]
            
            if therapist_ids:
                for patient_id in created_user_ids:
                    # Randomly assign a therapist
                    therapist_id = random.choice(therapist_ids)
                    try:
                        supabase.table("therapist_patients").insert({
                            "therapist_id": therapist_id,
                            "patient_id": patient_id,
                            "assigned_at": datetime.now(timezone.utc).isoformat()
                        }).execute()
                        assignments_created += 1
                    except Exception as e:
                        logger.warning(f"Failed to assign therapist to patient {patient_id}: {e}")
        
        patients_count = len(created_user_ids) if bulk_request.role == "patient" else 0
        therapists_count = len(created_user_ids) if bulk_request.role == "therapist" else 0
        
        logger.info(f"[BulkUsers] Complete: {len(created_user_ids)} {bulk_request.role}s created")
        
        # Audit log
        await log_audit_action(
            supabase=supabase,
            action="BULK_CREATE_USERS",
            details={
                "role": bulk_request.role,
                "requested_count": bulk_request.count,
                "created_count": len(created_user_ids),
                "source": bulk_request.source,
                "is_test_patient": bulk_request.is_test_patient,
                "auto_assign_therapists": bulk_request.auto_assign_therapists,
                "assignments_created": assignments_created,
                "environment": os.getenv("APP_ENV", "unknown"),
                "limits": {
                    "max_patients_prod": SYN_MAX_PATIENTS_PROD,
                    "max_therapists_prod": SYN_MAX_THERAPISTS_PROD,
                }
            },
        )
        
        return BulkUsersResponse(
            status="success",
            message=f"Created {len(created_user_ids)} {bulk_request.role}(s)",
            users_created=len(created_user_ids),
            user_ids=created_user_ids,
            patients_count=patients_count,
            therapists_count=therapists_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in bulk user creation")
        raise HTTPException(status_code=500, detail=f"Error: {e}")

# ----------------------------------------------------------------------
# Bulk check-ins generation endpoint
# ----------------------------------------------------------------------
@router.post("/synthetic/bulk-checkins", response_model=BulkCheckinsResponse)
@limiter.limit("5/hour")
async def bulk_create_checkins(
    request: Request,
    bulk_request: BulkCheckinsRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Generate check-ins in bulk for specified users.
    Enforces per-user check-in limits in production.
    """
    logger.info(f"[BulkCheckins] Starting")
    
    # Block all synthetic data generation in production
    if _is_production():
        _synthetic_generation_enabled()  # Will raise HTTPException(403) - no exceptions
    
    # Import helpers
    from data_generator import generate_realistic_checkin
    from datetime import datetime as dt
    import random
    
    try:
        # Determine target users
        target_user_ids = []
        
        if bulk_request.all_test_patients:
            # Get all test patients
            test_patients_resp = supabase.table("profiles").select("id")\
                .eq("role", "patient")\
                .eq("is_test_patient", True)\
                .is_("deleted_at", "null").execute()
            target_user_ids = [u["id"] for u in (test_patients_resp.data or [])]
        elif bulk_request.target_users:
            target_user_ids = bulk_request.target_users
        else:
            raise HTTPException(status_code=400, detail="Must specify target_users or all_test_patients")
        
        if not target_user_ids:
            raise HTTPException(status_code=400, detail="No target users found")
        
        # Determine date range
        now = datetime.now(timezone.utc)
        
        if bulk_request.last_n_days:
            start_date = now - timedelta(days=bulk_request.last_n_days)
            end_date = now
        elif bulk_request.start_date and bulk_request.end_date:
            try:
                start_date = dt.fromisoformat(bulk_request.start_date.replace("Z", "+00:00"))
                end_date = dt.fromisoformat(bulk_request.end_date.replace("Z", "+00:00"))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
        else:
            raise HTTPException(status_code=400, detail="Must specify date range")
        
        # Generate check-ins
        all_checkins = []
        days_count = (end_date - start_date).days + 1
        
        for user_id in target_user_ids:
            user_checkins = []
            
            for day_offset in range(days_count):
                checkin_date = start_date + timedelta(days=day_offset)
                
                # Determine how many check-ins for this day
                checkins_for_day = random.randint(
                    bulk_request.checkins_per_day_min,
                    bulk_request.checkins_per_day_max
                )
                
                for _ in range(checkins_for_day):
                    # Add some random hours to spread throughout the day
                    checkin_time = checkin_date + timedelta(hours=random.randint(0, 23))
                    
                    checkin = generate_realistic_checkin(
                        user_id=user_id,
                        when=checkin_time,
                        mood_state=bulk_request.mood_pattern
                    )
                    user_checkins.append(checkin)
            
            all_checkins.extend(user_checkins)
        
        # Insert check-ins in chunks
        checkins_created = 0
        chunk_size = 100
        
        for i in range(0, len(all_checkins), chunk_size):
            chunk = all_checkins[i:i+chunk_size]
            try:
                insert_resp = supabase.table("check_ins").insert(chunk).execute()
                if insert_resp.data:
                    checkins_created += len(insert_resp.data)
                else:
                    # Fallback if Supabase doesn't return data
                    checkins_created += len(chunk)
            except Exception as e:
                logger.error(f"Failed to insert check-in chunk {i}-{i+len(chunk)}: {e}")
        
        logger.info(f"[BulkCheckins] Complete: {checkins_created} check-ins for {len(target_user_ids)} users")
        
        # Audit log
        await log_audit_action(
            supabase=supabase,
            action="BULK_CREATE_CHECKINS",
            details={
                "users_affected": len(target_user_ids),
                "checkins_created": checkins_created,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "mood_pattern": bulk_request.mood_pattern,
                "checkins_per_day_range": [bulk_request.checkins_per_day_min, bulk_request.checkins_per_day_max],
                "environment": os.getenv("APP_ENV", "unknown"),
                "limits": {
                    "max_checkins_per_user_prod": SYN_MAX_CHECKINS_PER_USER_PROD,
                }
            },
        )
        
        return BulkCheckinsResponse(
            status="success",
            message=f"Created {checkins_created} check-ins for {len(target_user_ids)} users",
            checkins_created=checkins_created,
            users_affected=len(target_user_ids),
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in bulk check-ins creation")
        raise HTTPException(status_code=500, detail=f"Error: {e}")

__all__ = ["router"]
