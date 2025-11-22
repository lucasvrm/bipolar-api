"""
Admin endpoints for privileged operations.

These endpoints require admin authentication via JWT token with admin role.
"""
import logging
import os
import io
import csv
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from supabase import AsyncClient
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
from data_generator import generate_and_populate_data

logger = logging.getLogger("bipolar-api.admin")

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ----------------------------------------------------------------------
# Utils
# ----------------------------------------------------------------------
def _log_db_error(operation: str, error: Exception) -> None:
    """
    Log detalhado para erros de acesso ao banco.
    """
    logger.error(f"Erro em {operation}: {error}")
    if hasattr(error, "response"):
        logger.error(f"Raw response: {error.response}")


# ----------------------------------------------------------------------
# Endpoint: geração de dados sintéticos
# ----------------------------------------------------------------------
@router.post("/generate-data", response_model=SyntheticDataGenerationResponse)
@limiter.limit("5/hour")
async def generate_synthetic_data(
    request: Request,
    data_request: GenerateDataRequest,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
) -> Dict[str, Any]:
    # Check APP_ENV
    if os.getenv("APP_ENV") == "production" and not os.getenv("ALLOW_SYNTHETIC_IN_PROD"):
        raise HTTPException(
            status_code=403,
            detail="Synthetic data generation is disabled in production environment."
        )

    valid_patterns = ["stable", "cycling", "random", "manic", "depressive"]
    if data_request.moodPattern not in valid_patterns:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid moodPattern. Must be one of: {', '.join(valid_patterns)}",
        )

    patients_count = data_request.patientsCount or 0
    therapists_count = data_request.therapistsCount or 0

    if patients_count == 0 and therapists_count == 0:
        raise HTTPException(
            status_code=400,
            detail="É necessário ao menos 1 patient ou 1 therapist para gerar.",
        )

    if patients_count > 500:
        raise HTTPException(
            status_code=400,
            detail="Max limit of 500 patients exceeded.",
        )

    logger.info(
        f"Solicitação geração dados: patients={patients_count}, therapists={therapists_count}, "
        f"checkins={data_request.checkinsPerUser}, pattern={data_request.moodPattern}, "
        f"seed={data_request.seed}, clearDb={data_request.clearDb}"
    )
    start_ts = datetime.now(timezone.utc)

    try:
        if data_request.clearDb:
            logger.info("Limpando dados sintéticos antes de gerar...")
            synthetic_domains = ["@example.com", "@example.org", "@example.net"]
            resp_profiles = await supabase.table("profiles").select("id,email").execute()
            if resp_profiles.data:
                synthetic_ids = [
                    p["id"]
                    for p in resp_profiles.data
                    if p.get("email") and any(d in p["email"] for d in synthetic_domains)
                ]
                if synthetic_ids:
                    # Batch deletion
                    chunk_size = 100
                    for i in range(0, len(synthetic_ids), chunk_size):
                        chunk = synthetic_ids[i:i + chunk_size]
                        await supabase.table("check_ins").delete().in_("user_id", chunk).execute()
                        await supabase.table("profiles").delete().in_("id", chunk).execute()
                    logger.info(f"Limpou {len(synthetic_ids)} perfis sintéticos.")

        result = await generate_and_populate_data(
            supabase=supabase,
            patients_count=patients_count,
            therapists_count=therapists_count,
            checkins_per_patient=data_request.checkinsPerUser,
            pattern=data_request.moodPattern,
            clear_db=data_request.clearDb,
            seed=data_request.seed
        )

        stats = result.get("statistics", {})

        # Ensure stats has all fields
        stats_obj = {
            "users_created": stats.get("users_created", 0),
            "patients_created": stats.get("patients_created", 0),
            "therapists_created": stats.get("therapists_created", 0),
            "total_checkins": stats.get("total_checkins", 0),
            "mood_pattern": stats.get("mood_pattern", "unknown"),
            "checkins_per_user": stats.get("checkins_per_user", 0),
            "generated_at": stats.get("generated_at", datetime.now(timezone.utc).isoformat())
        }

        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
        logger.info(
            "Geração concluída em %.2fms", duration_ms
        )
        return {
            "status": "success",
            "statistics": stats_obj,
            "generatedAt": datetime.now(timezone.utc).isoformat()
        }

    except APIError as e:
        logger.exception("Erro de banco na geração de dados")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado na geração de dados")
        raise HTTPException(status_code=500, detail=f"Error generating synthetic data: {str(e)}")


# ----------------------------------------------------------------------
# Endpoint: estatísticas avançadas
# ----------------------------------------------------------------------
@router.get("/stats", response_model=StatsResponse)
async def get_admin_stats(
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info("Requisição de estatísticas avançadas recebida")
    start_ts = datetime.now(timezone.utc)

    try:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)
        thirty_days_ago = now - timedelta(days=30)

        # Contagem total de perfis
        profiles_head = await supabase.table("profiles").select(
            "*", count=CountMethod.exact, head=True
        ).execute()
        total_users = profiles_head.count or 0

        # Contagem total de check-ins
        checkins_head = await supabase.table("check_ins").select(
            "*", count=CountMethod.exact, head=True
        ).execute()
        total_checkins = checkins_head.count or 0

        # Perfil completo para separar real vs sintético
        synthetic_domains = ["@example.com", "@example.org", "@example.net"]
        profiles_resp = await supabase.table("profiles").select(
            "id,email,is_test_patient,role"
        ).execute()
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

        # Check-ins hoje
        today_resp = await supabase.table("check_ins").select(
            "*", count=CountMethod.exact, head=True
        ).gte("checkin_date", today_start.isoformat()).execute()
        checkins_today = today_resp.count or 0

        # Últimos 7 dias
        last7_resp = await supabase.table("check_ins").select(
            "*", count=CountMethod.exact, head=True
        ).gte("checkin_date", seven_days_ago.isoformat()).execute()
        checkins_last_7_days = last7_resp.count or 0

        # 7 dias anteriores aos últimos 7
        prev7_resp = await supabase.table("check_ins").select(
            "*", count=CountMethod.exact, head=True
        ).gte("checkin_date", fourteen_days_ago.isoformat()).lt(
            "checkin_date", seven_days_ago.isoformat()
        ).execute()
        checkins_last_7_days_previous = prev7_resp.count or 0

        # Check-ins últimos 30 dias
        last30_resp = await supabase.table("check_ins").select(
            "user_id, checkin_date, mood_data, meds_context_data, appetite_impulse_data"
        ).gte("checkin_date", thirty_days_ago.isoformat()).execute()
        checkins_30d = last30_resp.data or []

        # Pacientes ativos
        active_patients = {c["user_id"] for c in checkins_30d}
        active_patient_count = len(active_patients)
        avg_checkins_per_active_patient = (
            len(checkins_30d) / active_patient_count if active_patient_count > 0 else 0.0
        )

        # Adesão
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

        mood_counts = {
            "stable": 0,
            "hypomania": 0,
            "mania": 0,
            "depression": 0,
            "mixed": 0,
            "euthymic": 0,
        }
        mood_values: List[float] = []

        for c in checkins_30d:
            mood = c.get("mood_data", {})
            if isinstance(mood, dict):
                elevation = mood.get("elevation", 0)
                depression = mood.get("depressedMood", 0)
                activation = mood.get("activation", 0)
                energy = mood.get("energyLevel")

                if depression > 7 and elevation > 5:
                    mood_counts["mixed"] += 1
                    mood_values.append(3)
                elif elevation > 8 or (activation > 8 and (energy or 0) > 7):
                    mood_counts["mania"] += 1
                    mood_values.append(4)
                elif elevation > 5 or activation > 6:
                    mood_counts["hypomania"] += 1
                    mood_values.append(3.5)
                elif depression > 7:
                    mood_counts["depression"] += 1
                    mood_values.append(2)
                else:
                    mood_counts["euthymic"] += 1
                    mood_values.append(3)

        avg_current_mood = sum(mood_values) / len(mood_values) if mood_values else 3.0

        # Alerts críticos
        critical_alerts_last_30d = 0
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

        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
        logger.info(
            "Stats calculadas em %.2fms", duration_ms
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

    except APIError as e:
        logger.exception("Erro de banco ao obter stats")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado em stats")
        raise HTTPException(status_code=500, detail=f"Error retrieving statistics: {str(e)}")


# ----------------------------------------------------------------------
# Endpoint: cleanup (padronizado)
# ----------------------------------------------------------------------
@router.post("/cleanup", response_model=CleanupResponse)
@limiter.limit("5/hour")
async def cleanup_standard(
    request: Request,
    cleanup_request: CleanupDataRequest = None,
    dryRun: bool = False,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Endpoint simples para limpeza de dados sintéticos.
    Suporta query params para dryRun.
    """
    is_dry_run = dryRun
    if cleanup_request:
        if cleanup_request.dryRun:
            is_dry_run = True
        if not cleanup_request.confirm and not is_dry_run:
             raise HTTPException(
                status_code=400,
                detail="É necessário confirmar a limpeza. Use {'confirm': true} ou dryRun=true.",
            )

    logger.info(f"Cleanup request: dryRun={is_dry_run}")

    synthetic_domains = ["@example.com", "@example.org", "@example.net"]

    try:
        resp_profiles = await supabase.table("profiles").select("id,email").execute()

        ids_to_remove = []
        if resp_profiles.data:
            ids_to_remove = [
                p["id"]
                for p in resp_profiles.data
                if p.get("email") and any(d in p["email"] for d in synthetic_domains)
            ]

        if not is_dry_run and ids_to_remove:
             # Batch deletion
            chunk_size = 100
            for i in range(0, len(ids_to_remove), chunk_size):
                chunk = ids_to_remove[i:i + chunk_size]
                await supabase.table("check_ins").delete().in_("user_id", chunk).execute()
                await supabase.table("profiles").delete().in_("id", chunk).execute()

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
# Endpoint: danger zone cleanup (avançado)
# ----------------------------------------------------------------------
@router.post("/danger-zone-cleanup", response_model=CleanupResponse)
@limiter.limit("5/hour")
async def danger_zone_cleanup(
    request: Request,
    cleanup_request: DangerZoneCleanupRequest,
    supabase: AsyncClient = Depends(get_supabase_service),
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
        # Find candidates (is_test_patient=true)
        profiles_resp = await supabase.table("profiles").select(
            "id,email,created_at,is_test_patient,deleted_at"
        ).eq("is_test_patient", True).is_("deleted_at", "null").execute()

        test_patients = profiles_resp.data or []
        patients_to_delete = test_patients.copy()

        # Apply filters
        if cleanup_request.action == "delete_last_n":
            patients_to_delete.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            patients_to_delete = patients_to_delete[: cleanup_request.quantity]

        elif cleanup_request.action == "delete_by_mood":
            ids = [p["id"] for p in test_patients]
            if ids:
                ck_resp = await supabase.table("check_ins").select("user_id,mood_data").in_(
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
             # Batch deletion
            chunk_size = 100
            for i in range(0, len(ids_to_delete), chunk_size):
                chunk = ids_to_delete[i:i + chunk_size]
                # Child tables
                await supabase.table("check_ins").delete().in_("user_id", chunk).execute()
                try:
                    await supabase.table("crisis_plan").delete().in_("user_id", chunk).execute()
                    await supabase.table("clinical_notes").delete().in_("patient_id", chunk).execute()
                    await supabase.table("therapist_patients").delete().in_("patient_id", chunk).execute()
                    await supabase.table("user_consent").delete().in_("user_id", chunk).execute()
                except Exception:
                    pass
                await supabase.table("profiles").delete().in_("id", chunk).execute()

            # Audit log
            try:
                await supabase.table("audit_log").insert({
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
# Legacy support for /cleanup-data (redirect/wrapper)
# ----------------------------------------------------------------------
@router.post("/cleanup-data", response_model=CleanupResponse)
async def cleanup_data_legacy(
    request: Request,
    cleanup_request: CleanupDataRequest,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    return await cleanup_standard(request, cleanup_request, False, supabase, is_admin)

# ----------------------------------------------------------------------
# Legacy/Compatibility endpoints (kept to avoid breaking frontend if any)
# ----------------------------------------------------------------------
@router.post("/synthetic-data/clean", response_model=CleanDataResponse)
async def clean_synthetic_data_legacy(
    request: Request,
    clean_request: DangerZoneCleanupRequest,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    return await danger_zone_cleanup(request, clean_request, supabase, is_admin)


__all__ = ["router"]
