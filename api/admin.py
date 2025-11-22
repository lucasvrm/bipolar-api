"""
Admin endpoints for privileged operations.

These endpoints require admin authentication via JWT token with admin role.
"""
import logging
import io
import csv
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient
from postgrest.exceptions import APIError
from postgrest.types import CountMethod

from api.dependencies import (
    get_supabase_service,
    verify_admin_authorization,
)
from api.rate_limiter import limiter
from api.schemas.synthetic_data import (
    CleanDataRequest,
    CleanDataResponse,
    ToggleTestFlagResponse,
    EnhancedStatsResponse,
    DangerZoneCleanupRequest,
    DangerZoneCleanupResponse,
    SyntheticDataGenerationResponse,
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
    Inclui caso especial de ValidationError (possível resposta inesperada / RLS).
    """
    logger.error(f"Erro em {operation}: {error}")
    if hasattr(error, "response"):
        logger.error(f"Raw response: {error.response}")
    if isinstance(error, ValidationError):
        logger.critical("ValidationError - possível retorno de erro em vez de dados (RLS?).")
        logger.critical(str(error))


# ----------------------------------------------------------------------
# Modelos de requisição
# ----------------------------------------------------------------------
class GenerateDataRequest(BaseModel):
    """Corpo da requisição para geração de dados sintéticos."""
    model_config = {
        "json_schema_extra": {
            "example": {
                "patients_count": 5,
                "therapists_count": 2,
                "checkins_per_user": 30,
                "mood_pattern": "stable",
                "clear_db": False,
            }
        }
    }

    patients_count: Optional[int] = Field(default=2, ge=0, le=100)
    therapists_count: Optional[int] = Field(default=1, ge=0, le=50)
    checkins_per_user: int = Field(default=30, ge=1, le=365)
    mood_pattern: str = Field(default="stable")
    clear_db: bool = Field(default=False)

    # Parâmetro legado (cria todos como pacientes)
    num_users: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="DEPRECATED: usar patients_count e therapists_count"
    )


class CleanupDataRequest(BaseModel):
    """Confirmação para endpoint simples de limpeza."""
    model_config = {"json_schema_extra": {"example": {"confirm": True}}}
    confirm: bool = Field(default=False)


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
    valid_patterns = ["stable", "cycling", "random"]
    if data_request.mood_pattern not in valid_patterns:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mood_pattern. Must be one of: {', '.join(valid_patterns)}",
        )

    patients_count = data_request.patients_count
    therapists_count = data_request.therapists_count

    if data_request.num_users is not None:
        logger.info(
            f"Usando parâmetro legado num_users={data_request.num_users} (todos serão pacientes)"
        )
        patients_count = data_request.num_users
        therapists_count = 0

    if patients_count == 0 and therapists_count == 0:
        raise HTTPException(
            status_code=400,
            detail="É necessário ao menos 1 patient ou 1 therapist para gerar.",
        )

    logger.info(
        f"Solicitação geração dados: patients={patients_count}, therapists={therapists_count}, "
        f"checkins_per_patient={data_request.checkins_per_user}, pattern={data_request.mood_pattern}, "
        f"clear_db={data_request.clear_db}"
    )
    start_ts = datetime.now(timezone.utc)

    try:
        if data_request.clear_db:
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
                    await supabase.table("check_ins").delete().in_("user_id", synthetic_ids).execute()
                    await supabase.table("profiles").delete().in_("id", synthetic_ids).execute()
                    logger.info(f"Limpou {len(synthetic_ids)} perfis sintéticos.")

        result = await generate_and_populate_data(
            supabase=supabase,
            patients_count=patients_count,
            therapists_count=therapists_count,
            checkins_per_patient=data_request.checkins_per_user,
            pattern=data_request.mood_pattern,
            clear_db=data_request.clear_db,
        )

        stats = result.get("statistics", {})
        duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
        logger.info(
            "Geração concluída: users_created=%s patients=%s therapists=%s total_checkins=%s "
            "pattern=%s duration_ms=%.2f",
            stats.get("users_created"),
            stats.get("patients_created"),
            stats.get("therapists_created"),
            stats.get("total_checkins"),
            stats.get("mood_pattern"),
            duration_ms,
        )
        return result

    except APIError as e:
        logger.exception("Erro de banco na geração de dados")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado na geração de dados")
        raise HTTPException(status_code=500, detail=f"Error generating synthetic data: {str(e)}")


# ----------------------------------------------------------------------
# Endpoint: estatísticas avançadas
# ----------------------------------------------------------------------
@router.get("/stats", response_model=EnhancedStatsResponse)
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

        # 7 dias anteriores aos últimos 7 (para variação)
        prev7_resp = await supabase.table("check_ins").select(
            "*", count=CountMethod.exact, head=True
        ).gte("checkin_date", fourteen_days_ago.isoformat()).lt(
            "checkin_date", seven_days_ago.isoformat()
        ).execute()
        checkins_last_7_days_previous = prev7_resp.count or 0

        # Check-ins últimos 30 dias (dados detalhados)
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

        # Adesão (considerar camelCase + snake_case)
        adherence_values = []
        for c in checkins_30d:
            meds = c.get("meds_context_data", {})
            if isinstance(meds, dict):
                val = meds.get("medication_adherence")
                if val is None:
                    val = meds.get("medicationAdherence")
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
        energy_values: List[float] = []
        anxiety_values: List[float] = []

        for c in checkins_30d:
            mood = c.get("mood_data", {})
            if isinstance(mood, dict):
                elevation = mood.get("elevation", 0)
                depression = mood.get("depressedMood", 0)
                activation = mood.get("activation", 0)
                energy = mood.get("energyLevel")
                anxiety = mood.get("anxietyStress")

                if isinstance(energy, (int, float)):
                    energy_values.append(energy)
                if isinstance(anxiety, (int, float)):
                    anxiety_values.append(anxiety)

                # Classificação simples
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

        # Alerts críticos (considera ansiedade / energia)
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
            "Stats calculadas em %.2fms: real=%d sintético=%d checkins_7d=%d",
            duration_ms,
            real_patients_count,
            synthetic_patients_count,
            checkins_last_7_days,
        )

        return EnhancedStatsResponse(
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
# Endpoint: lista de usuários
# ----------------------------------------------------------------------
@router.get("/users", response_model=None)
async def get_admin_users(
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info("Requisição lista de usuários recebida")
    try:
        resp = await supabase.table("profiles").select("id,email").order("created_at", desc=True).limit(50).execute()
        users = resp.data or []
        logger.info(f"Retornando {len(users)} usuários")
        return users
    except APIError as e:
        logger.exception("Erro de banco ao listar usuários")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado ao listar usuários")
        raise HTTPException(status_code=500, detail=f"Error retrieving users: {str(e)}")


# ----------------------------------------------------------------------
# Endpoint: limpeza simples (legado)
# ----------------------------------------------------------------------
@router.post("/cleanup-data", response_model=None)
@limiter.limit("3/hour")
async def cleanup_synthetic_data(
    request: Request,
    cleanup_request: CleanupDataRequest,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    if not cleanup_request.confirm:
        raise HTTPException(
            status_code=400,
            detail="É necessário confirmar a limpeza. Use {'confirm': true}.",
        )

    logger.info("Requisição de cleanup simples recebida")

    try:
        resp_profiles = await supabase.table("profiles").select("id,email").execute()
        if not resp_profiles.data:
            return {
                "status": "success",
                "message": "No data to cleanup",
                "statistics": {
                    "profiles_deleted": 0,
                    "checkins_deleted": 0,
                    "cleaned_at": datetime.now(timezone.utc).isoformat(),
                },
            }

        synthetic_domains = ["@example.com", "@example.org", "@example.net"]
        synthetic_ids = [
            p["id"]
            for p in resp_profiles.data
            if p.get("email") and any(d in p["email"] for d in synthetic_domains)
        ]

        if not synthetic_ids:
            return {
                "status": "success",
                "message": "No synthetic users found",
                "statistics": {
                    "profiles_deleted": 0,
                    "checkins_deleted": 0,
                    "cleaned_at": datetime.now(timezone.utc).isoformat(),
                },
            }

        checkins_deleted = 0
        for uid in synthetic_ids:
            del_resp = await supabase.table("check_ins").delete().eq("user_id", uid).execute()
            if del_resp.data:
                checkins_deleted += len(del_resp.data)

        profiles_deleted = 0
        for uid in synthetic_ids:
            del_prof = await supabase.table("profiles").delete().eq("id", uid).execute()
            if del_prof.data:
                profiles_deleted += len(del_prof.data)

        return {
            "status": "success",
            "message": f"Cleaned up {profiles_deleted} synthetic users and {checkins_deleted} check-ins",
            "statistics": {
                "profiles_deleted": profiles_deleted,
                "checkins_deleted": checkins_deleted,
                "cleaned_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    except APIError as e:
        logger.exception("Erro de banco no cleanup")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado no cleanup")
        raise HTTPException(status_code=500, detail=f"Error cleaning up synthetic data: {str(e)}")


# ----------------------------------------------------------------------
# Endpoint: limpeza avançada (flexível)
# ----------------------------------------------------------------------
@router.post("/synthetic-data/clean", response_model=CleanDataResponse)
@limiter.limit("10/hour")
async def clean_synthetic_data(
    request: Request,
    clean_request: CleanDataRequest,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info(f"Synthetic data clean request: action={clean_request.action}")

    try:
        if clean_request.action == "delete_last_n" and not clean_request.quantity:
            raise HTTPException(status_code=400, detail="quantity é obrigatório para delete_last_n")
        if clean_request.action == "delete_before_date" and not clean_request.before_date:
            raise HTTPException(status_code=400, detail="before_date é obrigatório para delete_before_date")

        synthetic_domains = ["@example.com", "@example.org", "@example.net"]
        resp_profiles = await supabase.table("profiles").select("id,email,created_at,is_test_patient").execute()

        if not resp_profiles.data:
            return CleanDataResponse(status="success", message="No data to cleanup", deleted_count=0)

        synthetic_users = [
            p
            for p in resp_profiles.data
            if p.get("is_test_patient") is True
            or (p.get("email") and any(d in p["email"] for d in synthetic_domains))
        ]
        if not synthetic_users:
            return CleanDataResponse(status="success", message="No synthetic users found", deleted_count=0)

        users_to_delete = synthetic_users.copy()

        if clean_request.action == "delete_last_n":
            users_to_delete.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            users_to_delete = users_to_delete[: clean_request.quantity]

        elif clean_request.action == "delete_before_date":
            try:
                cutoff = datetime.fromisoformat(clean_request.before_date.replace("Z", "+00:00"))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
            users_to_delete = [
                u
                for u in users_to_delete
                if u.get("created_at")
                and datetime.fromisoformat(u["created_at"].replace("Z", "+00:00")) < cutoff
            ]

        elif clean_request.action == "delete_by_mood":
            raise HTTPException(
                status_code=501,
                detail="delete_by_mood não implementado. Use delete_all, delete_last_n ou delete_before_date.",
            )
        # delete_all -> sem filtro extra

        if not users_to_delete:
            return CleanDataResponse(
                status="success",
                message=f"No users matched criteria for {clean_request.action}",
                deleted_count=0,
            )

        ids = [u["id"] for u in users_to_delete]

        # Deleção em lote
        await supabase.table("check_ins").delete().in_("user_id", ids).execute()
        await supabase.table("profiles").delete().in_("id", ids).execute()

        deleted_count = len(ids)
        return CleanDataResponse(
            status="success",
            message=f"Deleted {deleted_count} synthetic patients and their data",
            deleted_count=deleted_count,
        )

    except HTTPException:
        raise
    except APIError as e:
        logger.exception("Erro de banco no synthetic-data/clean")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado no synthetic-data/clean")
        raise HTTPException(status_code=500, detail=f"Error cleaning synthetic data: {str(e)}")


# ----------------------------------------------------------------------
# Endpoint: exportação de dados sintéticos
# ----------------------------------------------------------------------
@router.get("/synthetic-data/export", response_model=None)
@limiter.limit("5/hour")
async def export_synthetic_data(
    request: Request,
    format: str = "json",
    scope: str = "all",
    quantity: Optional[int] = None,
    mood_pattern: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_checkins: bool = True,
    include_notes: bool = False,
    include_medications: bool = False,
    include_radar: bool = False,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info(f"Export request: format={format}, scope={scope}")
    try:
        if format not in ["csv", "json"]:
            raise HTTPException(status_code=400, detail="Invalid format. Must be csv or json.")

        if scope not in ["all", "last_n", "by_mood", "by_period"]:
            raise HTTPException(status_code=400, detail="Invalid scope.")

        if scope == "last_n" and not quantity:
            raise HTTPException(status_code=400, detail="quantity requerido para last_n.")

        if scope == "by_period" and (not start_date or not end_date):
            raise HTTPException(status_code=400, detail="start_date e end_date requeridos para by_period.")

        synthetic_domains = ["@example.com", "@example.org", "@example.net"]
        profiles_resp = await supabase.table("profiles").select("*").execute()
        if not profiles_resp.data:
            raise HTTPException(status_code=404, detail="No profiles found")

        synthetic_users = [
            p
            for p in profiles_resp.data
            if p.get("is_test_patient") is True
            or (p.get("email") and any(d in p["email"] for d in synthetic_domains))
        ]

        if scope == "last_n":
            synthetic_users.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            synthetic_users = synthetic_users[:quantity]

        elif scope == "by_period":
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
            synthetic_users = [
                u
                for u in synthetic_users
                if u.get("created_at")
                and start_dt
                <= datetime.fromisoformat(u["created_at"].replace("Z", "+00:00"))
                <= end_dt
            ]

        if not synthetic_users:
            raise HTTPException(status_code=404, detail="No synthetic users found matching criteria")

        export_data = []
        for user in synthetic_users:
            user_obj: Dict[str, Any] = {
                "id": user.get("id"),
                "email": user.get("email"),
                "role": user.get("role"),
                "created_at": user.get("created_at"),
                "is_test_patient": user.get("is_test_patient", False),
            }

            if include_checkins:
                ck_resp = await supabase.table("check_ins").select("*").eq("user_id", user["id"]).execute()
                checkins = ck_resp.data or []
                user_obj["checkins"] = checkins
                user_obj["checkins_count"] = len(checkins)

            if include_notes:
                user_obj["notes"] = []  # placeholder

            if include_medications:
                user_obj["medications"] = []  # placeholder

            if include_radar:
                user_obj["radar"] = []  # placeholder

            export_data.append(user_obj)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if format == "json":
            output = json.dumps(export_data, indent=2, default=str)
            return StreamingResponse(
                io.BytesIO(output.encode()),
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=synthetic_data_{timestamp}.json"
                },
            )

        # CSV
        output_csv = io.StringIO()
        if export_data:
            flat_rows = []
            for u in export_data:
                flat_rows.append(
                    {
                        "id": u.get("id"),
                        "email": u.get("email"),
                        "role": u.get("role"),
                        "created_at": u.get("created_at"),
                        "is_test_patient": u.get("is_test_patient"),
                        "checkins_count": u.get("checkins_count", 0),
                    }
                )
            writer = csv.DictWriter(output_csv, fieldnames=flat_rows[0].keys())
            writer.writeheader()
            writer.writerows(flat_rows)

        return StreamingResponse(
            io.BytesIO(output_csv.getvalue().encode()),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=synthetic_data_{timestamp}.csv"
            },
        )

    except HTTPException:
        raise
    except APIError as e:
        logger.exception("Erro de banco durante export")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado na exportação")
        raise HTTPException(status_code=500, detail=f"Error exporting data: {str(e)}")


# ----------------------------------------------------------------------
# Endpoint: toggle flag de teste
# ----------------------------------------------------------------------
@router.patch("/patients/{patient_id}/toggle-test-flag", response_model=ToggleTestFlagResponse)
async def toggle_test_patient_flag(
    patient_id: str,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info(f"Toggling is_test_patient para paciente {patient_id}")
    try:
        resp = await supabase.table("profiles").select("id,is_test_patient").eq("id", patient_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        patient = resp.data[0]
        current = patient.get("is_test_patient", False)
        new_flag = not current

        await supabase.table("profiles").update(
            {"is_test_patient": new_flag, "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", patient_id).execute()

        return ToggleTestFlagResponse(
            id=patient_id,
            is_test_patient=new_flag,
            message=f"is_test_patient flag toggled to {new_flag}",
        )
    except APIError as e:
        logger.exception("Erro de banco ao togglar flag")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado ao togglar flag")
        raise HTTPException(status_code=500, detail=f"Error toggling test flag: {str(e)}")


# ----------------------------------------------------------------------
# Endpoint: disparo manual de job de deleção
# ----------------------------------------------------------------------
@router.post("/run-deletion-job", response_model=None)
@limiter.limit("5/hour")
async def run_deletion_job_manually(
    request: Request,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    logger.info("Manual deletion job triggered")
    try:
        from jobs.scheduled_deletion import process_scheduled_deletions

        stats = await process_scheduled_deletions()
        logger.info(f"Deletion job done: {stats}")
        return {
            "status": "success",
            "message": "Deletion job completed successfully",
            "statistics": stats,
        }
    except Exception as e:
        logger.exception("Erro executando deletion job manual")
        raise HTTPException(status_code=500, detail=f"Error running deletion job: {str(e)}")


# ----------------------------------------------------------------------
# Endpoint: danger zone cleanup
# ----------------------------------------------------------------------
@router.post("/danger-zone-cleanup", response_model=DangerZoneCleanupResponse)
@limiter.limit("5/hour")
async def danger_zone_cleanup(
    request: Request,
    cleanup_request: DangerZoneCleanupRequest,
    supabase: AsyncClient = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    MOOD_VARIANCE_THRESHOLD = 2.0
    logger.info(f"Danger zone cleanup: action={cleanup_request.action}")

    if cleanup_request.action == "delete_last_n" and not cleanup_request.quantity:
        raise HTTPException(
            status_code=400,
            detail="quantity é obrigatório para delete_last_n",
        )
    if cleanup_request.action == "delete_by_mood" and not cleanup_request.mood_pattern:
        raise HTTPException(
            status_code=400,
            detail="mood_pattern é obrigatório para delete_by_mood",
        )
    if cleanup_request.action == "delete_before_date" and not cleanup_request.before_date:
        raise HTTPException(
            status_code=400,
            detail="before_date é obrigatório para delete_before_date",
        )

    try:
        profiles_resp = await supabase.table("profiles").select(
            "id,email,created_at,is_test_patient,deleted_at"
        ).eq("is_test_patient", True).is_("deleted_at", "null").execute()

        if not profiles_resp.data:
            return DangerZoneCleanupResponse(
                deleted=0, message="No test patients found matching criteria"
            )

        test_patients = profiles_resp.data
        patients_to_delete = test_patients.copy()

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
                raise HTTPException(status_code=400, detail=f"Invalid before_date format: {e}")
            patients_to_delete = [
                pt
                for pt in patients_to_delete
                if pt.get("created_at")
                and datetime.fromisoformat(pt["created_at"].replace("Z", "+00:00")) < cutoff
            ]

        # delete_all: sem filtro adicional

        if not patients_to_delete:
            return DangerZoneCleanupResponse(
                deleted=0,
                message=f"No test patients matched criteria for {cleanup_request.action}",
            )

        ids_to_delete = [p["id"] for p in patients_to_delete]
        deleted_count = len(ids_to_delete)

        # Child tables
        await supabase.table("check_ins").delete().in_("user_id", ids_to_delete).execute()
        try:
            await supabase.table("crisis_plan").delete().in_("user_id", ids_to_delete).execute()
        except Exception:
            pass
        try:
            await supabase.table("clinical_notes").delete().in_("patient_id", ids_to_delete).execute()
        except Exception:
            pass
        try:
            await supabase.table("therapist_patients").delete().in_("patient_id", ids_to_delete).execute()
        except Exception:
            pass
        try:
            await supabase.table("user_consent").delete().in_("user_id", ids_to_delete).execute()
        except Exception:
            pass

        await supabase.table("profiles").delete().in_("id", ids_to_delete).execute()

        # Audit log
        try:
            await supabase.table("audit_log").insert(
                {
                    "user_id": None,
                    "action": "synthetic_cleanup",
                    "details": {
                        "cleanup_action": cleanup_request.action,
                        "quantity": cleanup_request.quantity,
                        "mood_pattern": cleanup_request.mood_pattern,
                        "before_date": cleanup_request.before_date,
                        "deleted_count": deleted_count,
                        "deleted_user_ids": (
                            ids_to_delete[:10]
                            if len(ids_to_delete) > 10
                            else ids_to_delete
                        ),
                    },
                    "performed_by": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ).execute()
        except Exception as e:
            logger.warning(f"Falha ao registrar audit log: {e}")

        return DangerZoneCleanupResponse(
            deleted=deleted_count,
            message=f"Successfully deleted {deleted_count} test patient(s) and their data",
        )

    except APIError as e:
        logger.exception("Erro de banco no danger-zone-cleanup")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.exception("Erro inesperado no danger-zone-cleanup")
        raise HTTPException(status_code=500, detail=f"Error during cleanup: {str(e)}")


__all__ = ["router"]
