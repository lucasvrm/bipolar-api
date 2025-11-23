"""
Admin endpoints for privileged operations.

These endpoints require admin authentication via JWT token with admin role.
"""
import logging
import os
import io
import csv
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from supabase import Client
from postgrest.exceptions import APIError
from postgrest.types import CountMethod

from api.dependencies import (
    get_supabase_service,
    verify_admin_authorization,
)
from api.rate_limiter import limiter
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
    UserListItem
)
from data_generator import generate_and_populate_data

logger = logging.getLogger("bipolar-api.admin")

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# ================== CONFIG SINTÉTICO CONTROLADO (PRODUÇÃO) ==================
SYN_MAX_PATIENTS_PROD = int(os.getenv("SYNTHETIC_MAX_PATIENTS_PROD", "50"))
SYN_MAX_THERAPISTS_PROD = int(os.getenv("SYNTHETIC_MAX_THERAPISTS_PROD", "10"))
SYN_MAX_CHECKINS_PER_USER_PROD = int(os.getenv("SYNTHETIC_MAX_CHECKINS_PER_USER_PROD", "20"))
SYN_ALLOWED_DOMAINS = [
    d.strip() for d in os.getenv("SYNTHETIC_ALLOWED_DOMAINS", "@example.com,@example.org").split(",")
    if d.strip()
]

def _is_production() -> bool:
    return os.getenv("APP_ENV") == "production"

def _synthetic_generation_enabled() -> bool:
    if not _is_production():
        return True
    return bool(os.getenv("ALLOW_SYNTHETIC_IN_PROD"))

# ----------------------------------------------------------------------
# Utils
# ----------------------------------------------------------------------
def _log_db_error(operation: str, error: Exception) -> None:
    logger.error(f"Erro em {operation}: {error}")
    if hasattr(error, "response"):
        logger.error(f"Raw response: {error.response}")

# ----------------------------------------------------------------------
# Geração sintética (sem testMode)
# ----------------------------------------------------------------------
@router.post("/generate-data", response_model=SyntheticDataGenerationResponse)
@limiter.limit("5/hour")
async def generate_synthetic_data(
    request: Request,
    data_request: GenerateDataRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
) -> Dict[str, Any]:
    if _is_production():
        if not _synthetic_generation_enabled():
            raise HTTPException(
                status_code=403,
                detail="Synthetic data generation disabled em produção: defina ALLOW_SYNTHETIC_IN_PROD."
            )
        if data_request.clearDb:
            raise HTTPException(status_code=403, detail="clearDb não permitido em produção.")
        if (data_request.patientsCount or 0) > SYN_MAX_PATIENTS_PROD:
            raise HTTPException(status_code=400, detail=f"patientsCount excede limite ({SYN_MAX_PATIENTS_PROD}).")
        if (data_request.therapistsCount or 0) > SYN_MAX_THERAPISTS_PROD:
            raise HTTPException(status_code=400, detail=f"therapistsCount excede limite ({SYN_MAX_THERAPISTS_PROD}).")
        if (data_request.checkinsPerUser or 0) > SYN_MAX_CHECKINS_PER_USER_PROD:
            raise HTTPException(status_code=400, detail=f"checkinsPerUser excede limite ({SYN_MAX_CHECKINS_PER_USER_PROD}).")

    valid_patterns = ["stable", "cycling", "random", "manic", "depressive"]
    if data_request.moodPattern not in valid_patterns:
        raise HTTPException(status_code=400, detail=f"Invalid moodPattern. Must be one of: {', '.join(valid_patterns)}")

    patients_count = data_request.patientsCount or 0
    therapists_count = data_request.therapistsCount or 0
    if patients_count == 0 and therapists_count == 0:
        raise HTTPException(status_code=400, detail="É necessário ao menos 1 patient ou 1 therapist.")

    logger.info(
        f"[SyntheticGen] start patients={patients_count} therapists={therapists_count} "
        f"checkinsPerUser={data_request.checkinsPerUser} pattern={data_request.moodPattern} seed={data_request.seed} clearDb={data_request.clearDb}"
    )
    start_ts = datetime.now(timezone.utc)

    try:
        result = await generate_and_populate_data(
            supabase=supabase,
            patients_count=patients_count,
            therapists_count=therapists_count,
            checkins_per_patient=data_request.checkinsPerUser,
            pattern=data_request.moodPattern,
            clear_db=data_request.clearDb,
            seed=data_request.seed
        )

        stats = result.get("statistics", {}) if isinstance(result, dict) else {}
        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000

        stats_obj = {
            "users_created": stats.get("users_created", patients_count + therapists_count),
            "patients_created": stats.get("patients_created", patients_count),
            "therapists_created": stats.get("therapists_created", therapists_count),
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

        logger.info(
            "[SyntheticGen] concluída em %.2fms (patients=%d, therapists=%d)",
            duration_ms, patients_count, therapists_count
        )

        return {
            "status": "success",
            "statistics": stats_obj,
            "generatedAt": datetime.now(timezone.utc).isoformat()
        }

    except ValidationError as ve:
        logger.error(f"Validation error generating synthetic data: {ve}")
        raise HTTPException(status_code=400, detail="Validation error in synthetic data request.")
    except APIError as e:
        logger.exception("Erro de banco na geração de dados")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado na geração de dados sintéticos")
        raise HTTPException(status_code=500, detail=f"Error generating synthetic data: {str(e)}")

# ----------------------------------------------------------------------
# Estatísticas
# ----------------------------------------------------------------------
@router.get("/stats", response_model=StatsResponse)
async def get_admin_stats(
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info("Requisição de estatísticas avançadas recebida")
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

        try:
            profiles_head = supabase.table("profiles").select("*", count=CountMethod.exact, head=True).execute()
            total_users = profiles_head.count or 0
        except Exception as e:
            logger.warning(f"Error fetching total users count: {e}")

        try:
            checkins_head = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True).execute()
            total_checkins = checkins_head.count or 0
        except Exception as e:
            logger.warning(f"Error fetching total checkins count: {e}")

        try:
            synthetic_domains = ["@example.com", "@example.org", "@example.net"]
            profiles_resp = supabase.table("profiles").select("id,email,is_test_patient,role").execute()
            profiles_all = profiles_resp.data or []
            synthetic_patient_ids = set()
            real_patient_ids = set()
            for p in profiles_all:
                if p.get("role") == "patient":
                    if p.get("is_test_patient") is True or (
                        p.get("email") and any(d in p["email"] for d in synthetic_domains)
                    ):
                        synthetic_patient_ids.add(p["id"])
                    else:
                        real_patient_ids.add(p["id"])
            real_patients_count = len(real_patient_ids)
            synthetic_patients_count = len(synthetic_patient_ids)
        except Exception as e:
            logger.warning(f"Error categorizing patients: {e}")

        try:
            today_resp = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True).gte(
                "checkin_date", today_start.isoformat()
            ).execute()
            checkins_today = today_resp.count or 0
        except Exception as e:
            logger.warning(f"Error today's checkins: {e}")

        try:
            last7_resp = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True).gte(
                "checkin_date", seven_days_ago.isoformat()
            ).execute()
            checkins_last_7_days = last7_resp.count or 0
        except Exception as e:
            logger.warning(f"Error last7 checkins: {e}")

        try:
            prev7_resp = supabase.table("check_ins").select("*", count=CountMethod.exact, head=True).gte(
                "checkin_date", fourteen_days_ago.isoformat()
            ).lt("checkin_date", seven_days_ago.isoformat()).execute()
            checkins_last_7_days_previous = prev7_resp.count or 0
        except Exception as e:
            logger.warning(f"Error previous7 checkins: {e}")

        try:
            last30_resp = supabase.table("check_ins").select(
                "user_id, checkin_date, mood_data, meds_context_data, appetite_impulse_data, symptoms_data"
            ).gte("checkin_date", thirty_days_ago.isoformat()).execute()
            checkins_30d = last30_resp.data or []
            active_patients = {c["user_id"] for c in checkins_30d}
            active_patient_count = len(active_patients)
            avg_checkins_per_active_patient = (
                len(checkins_30d) / active_patient_count if active_patient_count > 0 else 0.0
            )
            adherence_values = []
            for c in checkins_30d:
                meds = c.get("meds_context_data", {})
                if isinstance(meds, dict):
                    val = meds.get("medicationAdherence") or meds.get("medication_adherence")
                    if isinstance(val, (int, float)):
                        adherence_values.append(val)
            avg_adherence_last_30d = (
                sum(adherence_values) / len(adherence_values) if adherence_values else 0.0
            )
            mood_values: List[float] = []
            for c in checkins_30d:
                mood = c.get("mood_data", {})
                if isinstance(mood, dict):
                    elevation = mood.get("elevation", 0)
                    depression = mood.get("depressedMood", 0)
                    activation = mood.get("activation", 0)
                    energy = mood.get("energyLevel")
                    if depression > 7 and elevation > 5:
                        mood_counts["mixed"] += 1; mood_values.append(3)
                    elif elevation > 8 or (activation > 8 and (energy or 0) > 7):
                        mood_counts["mania"] += 1; mood_values.append(4)
                    elif elevation > 5 or activation > 6:
                        mood_counts["hypomania"] += 1; mood_values.append(3.5)
                    elif depression > 7:
                        mood_counts["depression"] += 1; mood_values.append(2)
                    else:
                        mood_counts["euthymic"] += 1; mood_values.append(3)
            avg_current_mood = sum(mood_values) / len(mood_values) if mood_values else 3.0
            for c in checkins_30d:
                md = c.get("mood_data", {})
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
        except Exception as e:
            logger.warning(f"Error analyzing last30: {e}")

        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
        logger.info(
            "Stats calculadas em %.2fms: users=%d checkins=%d real=%d synthetic=%d",
            duration_ms, total_users, total_checkins, real_patients_count, synthetic_patients_count
        )

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
        logger.exception("Erro crítico stats")
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
    is_dry_run = dryRun
    if cleanup_request:
        if cleanup_request.dryRun:
            is_dry_run = True
        if not cleanup_request.confirm and not is_dry_run:
            raise HTTPException(status_code=400, detail="Confirmação necessária ou usar dryRun=true.")
    logger.info(f"Cleanup request: dryRun={is_dry_run}")

    synthetic_domains = ["@example.com", "@example.org", "@example.net"]
    try:
        resp_profiles = supabase.table("profiles").select("id,email").execute()
        ids_to_remove = []
        if resp_profiles.data:
            ids_to_remove = [
                p["id"]
                for p in resp_profiles.data
                if p.get("email") and any(d in p["email"] for d in synthetic_domains)
            ]
        if not is_dry_run && ids_to_remove:
            chunk_size = 100
            for i in range(0, len(ids_to_remove), chunk_size):
                chunk = ids_to_remove[i:i + chunk_size]
                supabase.table("check_ins").delete().in_("user_id", chunk).execute()
                supabase.table("profiles").delete().in_("id", chunk).execute()
        return CleanupResponse(
            status="ok",
            message=f"Cleanup {'simulated' if is_dry_run else 'completed'}",
            removedRecords=len(ids_to_remove),
            sampleIds=ids_to_remove[:5] if ids_to_remove else [],
            dryRun=is_dry_run,
            cleanedAt=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.exception("Erro no cleanup")
        raise HTTPException(status_code=500, detail=f"Cleanup error: {e}")

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
    logger.info(f"Danger zone cleanup: action={cleanup_request.action}, dryRun={cleanup_request.dryRun}")

    if cleanup_request.action == "delete_last_n" and not cleanup_request.quantity:
        raise HTTPException(status_code=400, detail="quantity required for delete_last_n")
    if cleanup_request.action == "delete_by_mood" and not cleanup_request.mood_pattern:
        raise HTTPException(status_code=400, detail="mood_pattern required for delete_by_mood")
    if cleanup_request.action == "delete_before_date" and not cleanup_request.before_date:
        raise HTTPException(status_code=400, detail="before_date required for delete_before_date")

    try:
        profiles_resp = supabase.table("profiles").select(
            "id,email,created_at,is_test_patient,deleted_at"
        ).eq("is_test_patient", True).is_("deleted_at", "null").execute()

        test_patients = profiles_resp.data or []
        patients_to_delete = test_patients.copy()

        if cleanup_request.action == "delete_last_n":
            patients_to_delete.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            patients_to_delete = patients_to_delete[: cleanup_request.quantity]

        elif cleanup_request.action == "delete_by_mood":
            ids = [p["id"] for p in test_patients]
            if ids:
                ck_resp = supabase.table("check_ins").select("user_id,mood_data").in_(
                    "user_id", ids
                ).execute()
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
                            elev = md.get("elevation", 0) or md.get("elevatedMood", 0)
                            depr = md.get("depressedMood", 0)
                            mood_score = (elev - depr) / 2.0
                            mood_values.append(mood_score)
                    if mood_values:
                        mean_mood = sum(mood_values) / len(mood_values)
                        variance = sum((x - mean_mood) ** 2 for x in mood_values) / len(mood_values)
                        pattern = cleanup_request.mood_pattern
                        if pattern == "stable" and variance < MOOD_VARIANCE_THRESHOLD:
                            filtered.append(pt)
                        elif pattern == "cycling" and variance >= MOOD_VARIANCE_THRESHOLD:
                            filtered.append(pt)
                        elif pattern == "random":
                            filtered.append(pt)
                patients_to_delete = filtered

        elif cleanup_request.action == "delete_before_date":
            try:
                cutoff = datetime.fromisoformat(cleanup_request.before_date.replace("Z", "+00:00"))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid date: {e}")
            patients_to_delete = [
                pt
                for pt in patients_to_delete
                if pt.get("created_at")
                and datetime.fromisoformat(pt["created_at"].replace("Z", "+00:00")) < cutoff
            ]

        ids_to_delete = [p["id"] for p in patients_to_delete]

        if not cleanup_request.dryRun and ids_to_delete:
            chunk_size = 100
            for i in range(0, len(ids_to_delete), chunk_size):
                chunk = ids_to_delete[i:i + chunk_size]
                supabase.table("check_ins").delete().in_("user_id", chunk).execute()
                try:
                    supabase.table("crisis_plan").delete().in_("user_id", chunk).execute()
                    supabase.table("clinical_notes").delete().in_("patient_id", chunk).execute()
                    supabase.table("therapist_patients").delete().in_("patient_id", chunk).execute()
                    supabase.table("user_consent").delete().in_("user_id", chunk).execute()
                except Exception:
                    pass
                supabase.table("profiles").delete().in_("id", chunk).execute()

            try:
                supabase.table("audit_log").insert({
                    "action": "danger_zone_cleanup",
                    "details": {
                        "action": cleanup_request.action,
                        "deleted_count": len(ids_to_delete)
                    },
                    "created_at": datetime.now(timezone.utc).isoformat()
                }).execute()
            except Exception:
                pass

        return CleanupResponse(
            status="ok",
            message=f"Danger zone cleanup {'simulated' if cleanup_request.dryRun else 'completed'}",
            removedRecords=len(ids_to_delete),
            sampleIds=ids_to_delete[:5],
            dryRun=cleanup_request.dryRun,
            cleanedAt=datetime.now(timezone.utc).isoformat()
        )

    except Exception as e:
        logger.exception("Erro no danger-zone-cleanup")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# ----------------------------------------------------------------------
# Legacy wrappers
# ----------------------------------------------------------------------
@router.post("/cleanup-data", response_model=CleanupResponse)
async def cleanup_data_legacy(
    request: Request,
    cleanup_request: CleanupDataRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    return await cleanup_standard(request, cleanup_request, False, supabase, is_admin)

@router.post("/synthetic-data/clean", response_model=CleanDataResponse)
async def clean_synthetic_data_legacy(
    request: Request,
    clean_request: DangerZoneCleanupRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    return await danger_zone_cleanup(request, clean_request, supabase, is_admin)

# ----------------------------------------------------------------------
# User Management (idempotente sem inserir perfil duplicado)
# ----------------------------------------------------------------------
@router.post("/users/create", response_model=CreateUserResponse)
@limiter.limit("10/hour")
async def create_user(
    request: Request,
    user_request: CreateUserRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info(f"[AdminCreateUser] email={user_request.email} role={user_request.role}")

    if user_request.role not in ("patient", "therapist"):
        raise HTTPException(status_code=400, detail="Role inválida (use 'patient' ou 'therapist').")
    if not user_request.password or len(user_request.password) < 8:
        raise HTTPException(status_code=400, detail="Senha deve ter ao menos 8 caracteres.")

    email_lower = user_request.email.strip().lower()

    # Verifica duplicata por email em profiles (idempotência)
    try:
        existing_profile = supabase.table("profiles").select("id,email").eq("email", email_lower).execute()
        if existing_profile.data:
            logger.warning(f"[AdminCreateUser] Email já existente em profiles: {email_lower}")
            raise HTTPException(status_code=409, detail=f"Email {email_lower} já está registrado")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[AdminCreateUser] Falha ao verificar duplicata em profiles: {e}")

    # Criação no Auth
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
        if "duplicate" in msg.lower() or "already" in msg.lower():
            logger.warning(f"[AdminCreateUser] Email já existe no Auth: {email_lower}")
            raise HTTPException(status_code=409, detail=f"Email {email_lower} já está registrado")
        logger.exception("[AdminCreateUser] Erro ao criar usuário no Auth")
        raise HTTPException(status_code=500, detail=f"Erro ao criar usuário no Auth: {msg}")

    # Extrair user_id
    user_id = None
    try:
        if getattr(auth_resp, "user", None):
            for attr in ("id", "uuid", "user_id"):
                val = getattr(auth_resp.user, attr, None)
                if isinstance(val, str) and val:
                    user_id = val
                    break
    except Exception:
        pass
    if not user_id and isinstance(auth_resp, dict):
        section = auth_resp.get("user") or auth_resp.get("data") or auth_resp
        if isinstance(section, dict):
            for k in ("id", "uuid", "user_id"):
                v = section.get(k)
                if isinstance(v, str) and v:
                    user_id = v
                    break
    if not user_id:
        logger.error(f"[AdminCreateUser] Falha ao extrair user_id; auth_resp={auth_resp}")
        raise HTTPException(status_code=500, detail="Falha ao extrair user_id do Auth.")

    # Atualiza perfil criado automaticamente (trigger). Fallback insert se não existir.
    profile_update_payload = {
        "role": user_request.role,
        "is_test_patient": False,
        "email": email_lower,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        update_resp = supabase.table("profiles").update(profile_update_payload).eq("id", user_id).execute()
        if not update_resp.data:
            logger.warning(f"[AdminCreateUser] Perfil não encontrado para id={user_id}, fazendo insert fallback.")
            insert_payload = {"id": user_id, **profile_update_payload}
            supabase.table("profiles").insert(insert_payload).execute()
        else:
            logger.info(f"[AdminCreateUser] Perfil atualizado para id={user_id}")
    except APIError as e:
        msg = str(e)
        logger.exception("[AdminCreateUser] Erro ao sincronizar perfil (APIError)")
        if "duplicate" in msg.lower() or "violates unique constraint" in msg.lower():
            pass
        raise HTTPException(status_code=500, detail=f"Erro ao sincronizar perfil: {msg}")
    except Exception as e:
        logger.exception("[AdminCreateUser] Erro inesperado ao sincronizar perfil")
        raise HTTPException(status_code=500, detail=f"Erro inesperado ao sincronizar perfil: {e}")

    logger.info(f"[AdminCreateUser] Usuário criado com sucesso id={user_id} email={email_lower}")
    return CreateUserResponse(
        status="success",
        message=f"Usuário {user_request.role} criado com sucesso",
        user_id=user_id,
        email=email_lower,
        role=user_request.role
    )

# ----------------------------------------------------------------------
# Listagem de usuários
# ----------------------------------------------------------------------
@router.get("/users", response_model=ListUsersResponse)
@limiter.limit("30/minute")
async def list_users(
    request: Request,
    role: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info(f"Admin listing users: role={role}, limit={limit}, offset={offset}")
    try:
        if limit > 200:
            limit = 200
        query = supabase.table("profiles").select(
            "id, email, role, created_at, is_test_patient"
        )
        if role:
            if role not in ["patient", "therapist"]:
                raise HTTPException(status_code=400, detail="Role deve ser 'patient' ou 'therapist'")
            query = query.eq("role", role)
        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        response = query.execute()
        data = response.data or []
        users = [
            UserListItem(
                id=u["id"],
                email=u["email"],
                role=u["role"],
                created_at=u["created_at"],
                is_test_patient=u.get("is_test_patient", False)
            )
            for u in data
        ]
        return ListUsersResponse(status="success", users=users, total=len(users))
    except HTTPException:
        raise
    except APIError as e:
        logger.exception(f"Database error listing users: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar usuários: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error listing users: {e}")
        raise HTTPException(status_code=500, detail=f"Erro inesperado ao listar usuários: {e}")

__all__ = ["router"]
