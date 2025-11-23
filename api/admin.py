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
    UserListItem
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
    if not _is_production():
        return True
    return bool(os.getenv("ALLOW_SYNTHETIC_IN_PROD"))

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

    if _is_production():
        if not _synthetic_generation_enabled():
            raise HTTPException(status_code=403, detail="Synthetic disabled em produção.")
        if data_request.clearDb:
            raise HTTPException(status_code=403, detail="clearDb não permitido em produção.")
        if (data_request.patientsCount or 0) > SYN_MAX_PATIENTS_PROD:
            raise HTTPException(status_code=400, detail=f"patientsCount excede limite {SYN_MAX_PATIENTS_PROD}.")
        if (data_request.therapistsCount or 0) > SYN_MAX_THERAPISTS_PROD:
            raise HTTPException(status_code=400, detail=f"therapistsCount excede limite {SYN_MAX_THERAPISTS_PROD}.")
        if (data_request.checkinsPerUser or 0) > SYN_MAX_CHECKINS_PER_USER_PROD:
            raise HTTPException(status_code=400, detail=f"checkinsPerUser excede limite {SYN_MAX_CHECKINS_PER_USER_PROD}.")

    patterns = ["stable", "cycling", "random", "manic", "depressive"]
    if data_request.moodPattern not in patterns:
        raise HTTPException(status_code=400, detail=f"moodPattern inválido. Use: {', '.join(patterns)}")

    patients_count = data_request.patientsCount or 0
    therapists_count = data_request.therapistsCount or 0
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
    limit: int = 50,
    offset: int = 0,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    if limit > 200:
        limit = 200
    query = supabase.table("profiles").select("id,email,role,created_at,is_test_patient")
    if role:
        if role not in ["patient", "therapist"]:
            raise HTTPException(status_code=400, detail="Role deve ser patient ou therapist.")
        query = query.eq("role", role)
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
                is_test_patient=u.get("is_test_patient", False)
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

__all__ = ["router"]
