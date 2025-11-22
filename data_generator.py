import asyncio
import logging
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

logger = logging.getLogger("bipolar-api.data_generator")
logger.addHandler(logging.NullHandler())

# =========================================================
# Utilidades básicas
# =========================================================
def _random_localpart(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length))


def _random_email() -> str:
    return f"{_random_localpart()}@example.org"


def _random_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(random.choices(alphabet, k=length))


# =========================================================
# Extração robusta de user_id
# =========================================================
def _extract_user_id_from_auth_resp(auth_resp: Any) -> str:
    try:
        user_obj = getattr(auth_resp, "user", None)
        if user_obj is not None:
            for attr in ("id", "user_id", "uuid", "uid", "value"):
                v = getattr(user_obj, attr, None)
                if isinstance(v, str) and v:
                    return v
            d = getattr(user_obj, "__dict__", None)
            if isinstance(d, dict):
                for _, v in d.items():
                    if isinstance(v, str) and v:
                        return v
    except Exception:
        pass

    for attr in ("id", "user_id", "uuid", "uid", "value"):
        v = getattr(auth_resp, attr, None)
        if isinstance(v, str) and v:
            return v

    try:
        d = getattr(auth_resp, "__dict__", None)
        if isinstance(d, dict):
            for _, v in d.items():
                if isinstance(v, str) and v:
                    return v
    except Exception:
        pass

    if isinstance(auth_resp, (tuple, list)) and auth_resp and isinstance(auth_resp[0], str):
        return auth_resp[0]

    try:
        s = str(auth_resp)
        if isinstance(s, str) and len(s) > 3:
            return s
    except Exception:
        pass

    return "<unknown-id>"


# =========================================================
# Criação de usuário com retry
# =========================================================
async def create_user_with_retry(
    client: Any,
    role: str,
    max_retries: int = 3,
    backoff_seconds: float = 0.1,
) -> Tuple[str, str, str]:
    password = _random_password()
    last_err_msg: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        email = _random_email()
        logger.debug("Tentativa %d/%d: criando %s → %s", attempt, max_retries, role, email)
        try:
            auth_resp = await client.auth.admin.create_user({"email": email, "password": password})
            user_id = _extract_user_id_from_auth_resp(auth_resp)
            logger.debug("Usuário auth criado: %s", user_id)
            payload = {"id": user_id, "email": email, "role": role}
            await client.table("profiles").insert(payload).execute()
            return user_id, email, password
        except Exception as e:
            last_err_msg = str(e)
            logger.warning("Duplicata/erro na tentativa %d, retry...", attempt)
            await asyncio.sleep(backoff_seconds * attempt)
            continue

    detail = f"Falha após todas as tentativas ({last_err_msg or 'duplicate'})"
    raise HTTPException(status_code=500, detail=detail)


# =========================================================
# Mapas de estados de humor
# =========================================================
_MOOD_STATE_MAP = {
    "MANIC":        {"mood": 5, "elevation": 9, "depressedMood": 1, "activation": 9, "notes": "Estado de mania"},
    "HYPOMANIC":    {"mood": 4, "elevation": 7, "depressedMood": 2, "activation": 7, "notes": "Estado hipomaníaco"},
    "DEPRESSED":    {"mood": 2, "elevation": 2, "depressedMood": 8, "activation": 3, "notes": "Estado depressivo"},
    "MIXED":        {"mood": 2, "elevation": 7, "depressedMood": 8, "activation": 7, "notes": "Estado misto"},
    "STABLE":       {"mood": 3, "elevation": 5, "depressedMood": 3, "activation": 5, "notes": "Estado estável"},
    "EUTHYMIC":     {"mood": 3, "elevation": 5, "depressedMood": 3, "activation": 5, "notes": "Humor eutímico"},
    "RANDOM":       None,
}


def _random_state_payload() -> Dict[str, Any]:
    elevation = random.randint(1, 9)
    depression = random.randint(1, 9)
    activation = random.randint(1, 9)
    mood = max(1, min(5, round((elevation - depression + activation) / 3)))
    notes = "Bom dia" if mood >= 4 else ("Mau humor" if mood <= 2 else "")
    return {
        "mood": mood,
        "elevation": elevation,
        "depressedMood": depression,
        "activation": activation,
        "notes": notes,
    }


# =========================================================
# Construção de blocos derivados
# =========================================================
def _build_sleep_data(state_key: Optional[str]) -> Dict[str, Any]:
    if state_key in ("MANIC", "HYPOMANIC"):
        hours = round(random.uniform(3.0, 6.0), 1)
    elif state_key == "DEPRESSED":
        hours = round(random.uniform(8.0, 11.0), 1)
    elif state_key == "MIXED":
        hours = round(random.uniform(4.0, 8.0), 1)
    elif state_key in ("STABLE", "EUTHYMIC"):
        hours = round(random.uniform(6.0, 8.0), 1)
    else:
        hours = round(random.uniform(4.0, 9.0), 1)
    sleep_quality = (
        "poor" if hours < 5
        else "fair" if hours < 6.5
        else "good" if hours < 8.5
        else "excellent"
    )
    return {
        "hoursSlept": hours,
        "sleepQuality": sleep_quality,
        "quality": sleep_quality,  # alias
    }


def _build_symptoms_data(state_key: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    if state_key == "MANIC":
        return {
            "thoughtSpeed": random.randint(7, 9),
            "irritability": random.randint(4, 8),
            "impulsivity": random.randint(6, 9),
            "psychomotorActivation": random.randint(7, 9),
            "sleepNeedReduced": True,
        }
    if state_key == "HYPOMANIC":
        return {
            "thoughtSpeed": random.randint(6, 8),
            "irritability": random.randint(3, 6),
            "impulsivity": random.randint(5, 7),
            "psychomotorActivation": random.randint(6, 8),
            "sleepNeedReduced": True,
        }
    if state_key == "DEPRESSED":
        return {
            "thoughtSpeed": random.randint(1, 4),
            "anergia": random.randint(6, 9),
            "psychomotorRetardation": random.randint(5, 8),
            "hopelessness": random.randint(6, 9),
            "sleepNeedReduced": False,
        }
    if state_key == "MIXED":
        return {
            "thoughtSpeed": random.randint(6, 9),
            "irritability": random.randint(5, 8),
            "moodLability": random.randint(6, 9),
            "impulsivity": random.randint(5, 8),
            "sleepNeedReduced": False,
        }
    if state_key in ("STABLE", "EUTHYMIC"):
        return {
            "thoughtSpeed": random.randint(3, 6),
            "resilience": random.randint(5, 8),
            "stressLevel": random.randint(2, 5),
            "sleepNeedReduced": False,
        }
    return {
        "thoughtSpeed": random.randint(1, 9),
        "irritability": random.randint(1, 9),
        "impulsivity": random.randint(1, 9),
        "moodLability": random.randint(1, 9),
        "sleepNeedReduced": random.choice([True, False]),
    }


def _build_risk_routine_data(state_key: Optional[str], mood: int) -> Dict[str, Any]:
    suicidal_thoughts = False
    self_harm_urges = False
    adherence = round(random.uniform(0.6, 1.0), 2)
    routine_disruption = random.randint(0, 10)

    if state_key == "DEPRESSED":
        suicidal_thoughts = random.random() < 0.15
        self_harm_urges = random.random() < 0.10
        routine_disruption = random.randint(4, 9)
    elif state_key == "MANIC":
        self_harm_urges = random.random() < 0.05
        routine_disruption = random.randint(6, 10)
    elif state_key == "MIXED":
        suicidal_thoughts = random.random() < 0.10
        self_harm_urges = random.random() < 0.07
        routine_disruption = random.randint(5, 9)
    elif state_key == "HYPOMANIC":
        routine_disruption = random.randint(3, 7)
    elif state_key in ("STABLE", "EUTHYMIC"):
        routine_disruption = random.randint(1, 4)
    else:
        routine_disruption = random.randint(0, 8)
        suicidal_thoughts = random.random() < 0.05
        self_harm_urges = random.random() < 0.04

    return {
        "suicidalThoughts": suicidal_thoughts,
        "selfHarmUrges": self_harm_urges,
        "medicationAdherence": adherence,
        "medication_adherence": adherence,  # alias
        "routineDisruption": routine_disruption,
        "socialIsolation": random.randint(0, 10),
        "riskScore": min(
            10,
            (
                (2 if suicidal_thoughts else 0)
                + (1 if self_harm_urges else 0)
                + (routine_disruption / 2)
                + (10 - adherence * 10) / 5
            ),
        ),
    }


def _compute_compulsion_intensity(impulse_control: int, binge: bool, spending: bool) -> int:
    """
    compulsionIntensity: métrica 1–9 derivada da perda de controle.
    Regra:
      base = (10 - impulse_control) + (2 se binge) + (2 se spending)
      normalização simples para faixa 1–9.
    """
    base = (10 - impulse_control) + (2 if binge else 0) + (2 if spending else 0)
    # base min 1 (impulse_control=9, nada ativado) max teórico (impulse_control=1, binge, spending) = (9)+(2)+(2)=13
    scaled = int(round((base / 13) * 9))
    return max(1, min(9, scaled))


def _build_appetite_impulse_data(state_key: Optional[str]) -> Dict[str, Any]:
    if state_key in ("MANIC", "HYPOMANIC"):
        appetite = random.randint(3, 8)
        binge = random.random() < 0.15
        spending = random.random() < 0.20
        impulse_control = random.randint(1, 4)
    elif state_key == "DEPRESSED":
        appetite = random.randint(1, 7)
        binge = random.random() < 0.10
        spending = random.random() < 0.05
        impulse_control = random.randint(5, 8)
    elif state_key == "MIXED":
        appetite = random.randint(1, 9)
        binge = random.random() < 0.18
        spending = random.random() < 0.15
        impulse_control = random.randint(2, 6)
    elif state_key in ("STABLE", "EUTHYMIC"):
        appetite = random.randint(4, 6)
        binge = random.random() < 0.05
        spending = random.random() < 0.03
        impulse_control = random.randint(6, 9)
    else:  # RANDOM
        appetite = random.randint(1, 9)
        binge = random.random() < 0.12
        spending = random.random() < 0.10
        impulse_control = random.randint(1, 9)

    compulsion_intensity = _compute_compulsion_intensity(impulse_control, binge, spending)

    return {
        "appetiteLevel": appetite,
        "bingeEatingUrges": binge,
        "impulseControl": impulse_control,
        "compulsiveSpending": spending,
        "compulsionIntensity": compulsion_intensity,      # campo exigido
        "compulsion_intensity": compulsion_intensity,     # alias
    }


def _build_meds_context_data(state_key: Optional[str]) -> Dict[str, Any]:
    adherence = round(random.uniform(0.6, 1.0), 2)
    side_effects_pool = ["nausea", "tremor", "sedation", "headache", "dryMouth"]
    if state_key in ("MANIC", "MIXED"):
        side_effects = random.sample(side_effects_pool, k=random.randint(1, 3))
    elif state_key == "DEPRESSED":
        side_effects = random.sample(side_effects_pool, k=random.randint(0, 2))
    else:
        side_effects = random.sample(side_effects_pool, k=random.randint(0, 1))

    missed = max(0, int((1 - adherence) * 7))
    now = datetime.now(timezone.utc)
    last_dose_hours_ago = round(random.uniform(2, 14), 1)
    next_dose_in_hours = round(random.uniform(4, 12), 1)
    timing_score = max(0, min(100, int((1 - missed / 7) * 100 - random.uniform(0, 10))))

    medication_timing = {
        "lastDoseUtc": (now - timedelta(hours=last_dose_hours_ago)).isoformat().replace("+00:00", "Z"),
        "nextDoseDueUtc": (now + timedelta(hours=next_dose_in_hours)).isoformat().replace("+00:00", "Z"),
        "lastDoseHoursAgo": last_dose_hours_ago,
        "nextDoseInHours": next_dose_in_hours,
        "onTimeScore": timing_score,
        "lateDosesThisWeek": max(0, missed - random.randint(0, missed)),
    }

    return {
        "medicationAdherence": adherence,
        "medication_adherence": adherence,    # alias
        "tookAllMeds": adherence > 0.85,
        "sideEffects": side_effects,
        "missedDoses": missed,
        "medicationTiming": medication_timing,
    }


def _compute_anxiety_stress(payload: Dict[str, Any], state_key: Optional[str]) -> int:
    base = payload["activation"] + (9 - payload["elevation"]) + payload["depressedMood"]
    if state_key == "MANIC":
        factor = 0.6
    elif state_key == "HYPOMANIC":
        factor = 0.7
    elif state_key == "DEPRESSED":
        factor = 0.85
    elif state_key == "MIXED":
        factor = 0.9
    elif state_key in ("STABLE", "EUTHYMIC"):
        factor = 0.5
    else:
        factor = 0.75
    score = int(round(base * factor / 3))
    return max(1, min(9, score))


# =========================================================
# generate_realistic_checkin
# =========================================================
def generate_realistic_checkin(
    user_id: str,
    when: Optional[datetime] = None,
    mood_state: Optional[str] = None,
) -> Dict[str, Any]:
    if when is None:
        when = datetime.now(timezone.utc)

    state_key = (mood_state or "").strip().upper() or None
    if state_key and state_key not in _MOOD_STATE_MAP:
        state_key = "RANDOM"

    if not state_key or _MOOD_STATE_MAP.get(state_key) is None:
        payload = _random_state_payload()
    else:
        payload = _MOOD_STATE_MAP[state_key].copy()

    sleep_data = _build_sleep_data(state_key)
    symptoms_data = _build_symptoms_data(state_key, payload)
    risk_routine_data = _build_risk_routine_data(state_key, payload["mood"])
    appetite_impulse_data = _build_appetite_impulse_data(state_key)
    meds_context_data = _build_meds_context_data(state_key)
    anxiety_stress = _compute_anxiety_stress(payload, state_key)
    energy_level = max(1, min(10, round((payload["activation"] + payload["elevation"]) / 2)))

    return {
        "user_id": user_id,
        "checkin_date": when.isoformat().replace("+00:00", "Z"),
        "mood": payload["mood"],
        "notes": payload["notes"],
        "mood_data": {
            "elevation": payload["elevation"],
            "depressedMood": payload["depressedMood"],
            "activation": payload["activation"],
            "energyLevel": energy_level,
            "anxietyStress": anxiety_stress,
        },
        "sleep_data": sleep_data,
        "symptoms_data": symptoms_data,
        "risk_routine_data": risk_routine_data,
        "appetite_impulse_data": appetite_impulse_data,
        "meds_context_data": meds_context_data,
    }


# =========================================================
# generate_user_checkin_history
# =========================================================
def generate_user_checkin_history(
    user_id: str,
    num_checkins: int = 20,
    mood_pattern: str = "stable",
) -> List[Dict[str, Any]]:
    mood_pattern = (mood_pattern or "stable").lower()
    if mood_pattern not in ("stable", "cycling", "random"):
        mood_pattern = "random"

    now = datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []

    for i in range(num_checkins):
        when = now - timedelta(hours=num_checkins - i)
        if mood_pattern == "stable":
            state = "STABLE"
        elif mood_pattern == "cycling":
            state = "HYPOMANIC" if (i // 3) % 2 == 0 else "DEPRESSED"
        else:
            state = random.choice(["MANIC", "DEPRESSED", "HYPOMANIC", "MIXED", "STABLE", "EUTHYMIC"])
        out.append(generate_realistic_checkin(user_id=user_id, when=when, mood_state=state))

    out.sort(key=lambda x: x["checkin_date"])
    return out


# =========================================================
# Suporte à geração via endpoint admin
# =========================================================
async def _create_multiple_for_role(
    client: Any,
    role: str,
    count: int,
    concurrency: int = 5,
) -> List[Tuple[str, str, str]]:
    semaphore = asyncio.Semaphore(concurrency)
    created: List[Tuple[str, str, str]] = []

    async def _one(idx: int):
        async with semaphore:
            try:
                return await create_user_with_retry(client, role)
            except Exception:
                logger.exception("Erro criando %s #%d", role, idx + 1)
                return None

    tasks = [asyncio.create_task(_one(i)) for i in range(count)]
    results = await asyncio.gather(*tasks)
    for r in results:
        if r:
            created.append(r)
    return created


async def generate_and_populate_data(
    supabase: Any,
    patients_count: int = 0,
    therapists_count: int = 0,
    checkins_per_patient: int = 30,
    pattern: str = "stable",
    clear_db: bool = False,
    concurrency: int = 5,
    **_ignored,
) -> Dict[str, Any]:
    if clear_db:
        logger.info("clear_db=True (simulado)")

    patient_tuples: List[Tuple[str, str, str]] = []
    if patients_count > 0:
        patient_tuples = await _create_multiple_for_role(supabase, "patient", patients_count, concurrency)
    therapist_tuples: List[Tuple[str, str, str]] = []
    if therapists_count > 0:
        therapist_tuples = await _create_multiple_for_role(supabase, "therapist", therapists_count, concurrency)

    patient_ids = [t[0] for t in patient_tuples]
    therapist_ids = [t[0] for t in therapist_tuples]
    all_ids = patient_ids + therapist_ids

    total_checkins = 0
    if patient_ids and checkins_per_patient > 0:
        batch: List[Dict[str, Any]] = []
        for pid in patient_ids:
            sub = generate_user_checkin_history(
                pid,
                num_checkins=checkins_per_patient,
                mood_pattern=pattern.lower(),
            )
            batch.extend(sub)
        total_checkins = len(batch)
        if batch:
            try:
                await supabase.table("check_ins").insert(batch).execute()
            except Exception as e:
                logger.warning("Falha ao inserir check-ins (prosseguindo): %s", e)

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    statistics = {
        "patients_created": len(patient_ids),
        "therapists_created": len(therapist_ids),
        "users_created": len(all_ids),
        "user_ids": all_ids,
        "patient_ids": patient_ids,
        "therapist_ids": therapist_ids,
        "checkins_per_user": checkins_per_patient,
        "mood_pattern": pattern,
        "total_checkins": total_checkins,
        "generated_at": generated_at,
    }

    logger.info(
        "generate_and_populate_data: pacientes=%d terapeutas=%d users=%d checkins=%d pattern=%s",
        len(patient_ids), len(therapist_ids), len(all_ids), total_checkins, pattern
    )

    return {
        "status": "success",
        "statistics": statistics,
        "patient_ids": patient_ids,
        "therapist_ids": therapist_ids,
    }


__all__ = [
    "create_user_with_retry",
    "generate_and_populate_data",
    "generate_realistic_checkin",
    "generate_user_checkin_history",
]
