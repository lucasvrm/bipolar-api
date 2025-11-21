"""
Data generator module for creating synthetic realistic bipolar disorder check-in data.

This module provides functionality to generate synthetic patient data with realistic
patterns for bipolar disorder monitoring, mapped correctly to the database JSONB schema.
"""
import random
from datetime import datetime, timedelta, timezone
from faker import Faker
from typing import List, Dict, Any, Optional
from supabase import AsyncClient
import logging
from fastapi import HTTPException
from api.schemas.checkin_jsonb import (
    SleepData,
    MoodData,
    SymptomsData,
    RiskRoutineData,
    AppetiteImpulseData,
    MedsContextData
)

# Use a specific locale for consistency
fake = Faker('pt_BR')
logger = logging.getLogger("bipolar-api.data_generator")


def generate_realistic_checkin(
    user_id: str,
    checkin_date: datetime,
    mood_state: str = None
) -> Dict[str, Any]:
    """
    Generate a single realistic check-in with correlated features,
    structured into the specific JSONB columns of the database.
    """
    # Define mood state if not provided
    if mood_state is None:
        mood_state = random.choices(
            ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
            weights=[0.5, 0.25, 0.15, 0.10]
        )[0]
    
    # --- 1. Generate Raw Values based on Clinical Logic ---
    
    if mood_state == 'MANIC':
        # Manic: Low sleep, high energy, high activation/elevation, risky behavior
        sleep_hours = round(random.uniform(3.0, 6.0), 1)
        sleep_quality = random.randint(3, 7)
        energy_level = random.randint(7, 10)
        depressed_mood = random.randint(0, 3)
        anxiety_stress = random.randint(5, 10)
        activation = random.randint(7, 10)
        elevation = random.randint(7, 10)
        thought_speed = random.randint(7, 10)
        distractibility = random.randint(6, 10)
        libido = random.randint(6, 10)
        compulsion_episode = random.choice([0, 1])
        compulsion_intensity = random.randint(3, 5) if compulsion_episode else 0
        motivation = random.randint(8, 10)
        tasks_planned = random.randint(5, 15)
        tasks_completed = random.randint(1, tasks_planned) # Often starts many, finishes few or many
        
    elif mood_state == 'DEPRESSED':
        # Depressed: High sleep, low energy, low motivation, rumination
        sleep_hours = round(random.uniform(8.0, 12.0), 1)
        sleep_quality = random.randint(2, 6)
        energy_level = random.randint(1, 4)
        depressed_mood = random.randint(6, 10)
        anxiety_stress = random.randint(4, 9)
        activation = random.randint(0, 3)
        elevation = random.randint(0, 2)
        thought_speed = random.randint(1, 4)
        distractibility = random.randint(2, 6)
        libido = random.randint(0, 3)
        compulsion_episode = 0
        compulsion_intensity = 0
        motivation = random.randint(1, 4)
        tasks_planned = random.randint(1, 5)
        tasks_completed = max(0, random.randint(0, tasks_planned // 2))

    elif mood_state == 'MIXED':
        # Mixed: Erratic sleep, high energy but bad mood, high anxiety/agitation
        sleep_hours = round(random.uniform(4.0, 7.0), 1)
        sleep_quality = random.randint(2, 5)
        energy_level = random.randint(3, 7)
        depressed_mood = random.randint(6, 9)
        anxiety_stress = random.randint(7, 10)
        activation = random.randint(5, 8)
        elevation = random.randint(2, 5)
        thought_speed = random.randint(5, 8)
        distractibility = random.randint(7, 10)
        libido = random.randint(2, 6)
        compulsion_episode = random.choice([0, 1])
        compulsion_intensity = random.randint(2, 4) if compulsion_episode else 0
        motivation = random.randint(2, 6)
        tasks_planned = random.randint(3, 8)
        tasks_completed = random.randint(0, tasks_planned // 2)

    else:  # EUTHYMIC
        # Stable: Normal ranges
        sleep_hours = round(random.uniform(6.5, 8.5), 1)
        sleep_quality = random.randint(6, 9)
        energy_level = random.randint(5, 8)
        depressed_mood = random.randint(0, 4)
        anxiety_stress = random.randint(0, 5)
        activation = random.randint(4, 7)
        elevation = random.randint(3, 6)
        thought_speed = random.randint(4, 7)
        distractibility = random.randint(2, 5)
        libido = random.randint(4, 7)
        compulsion_episode = 0
        compulsion_intensity = 0
        motivation = random.randint(4, 8)
        tasks_planned = random.randint(3, 8)
        tasks_completed = random.randint(tasks_planned // 2, tasks_planned)

    # Secondary variables derived from core state
    medication_adherence = 1 if (mood_state == 'EUTHYMIC' or random.random() > 0.3) else 0
    medication_timing = random.randint(0, 1) if medication_adherence else 0
    medication_change_recent = 1 if random.random() < 0.05 else 0
    
    social_connection = max(0, min(10, 10 - anxiety_stress // 2 + random.randint(-2, 2)))
    contextual_stressors = random.randint(0, 1)
    social_rhythm_event = 1 if random.random() < 0.15 else 0 # Ex: travel, shift work
    
    # Risk factors with correlations
    suicidal_ideation = random.randint(0, 3) if mood_state == 'DEPRESSED' else 0
    suicide_risk = random.randint(0, 2) if suicidal_ideation > 0 else 0
    self_harm = random.randint(0, 1) if mood_state in ['DEPRESSED', 'MIXED'] else 0
    routine_disruption = 1 if social_rhythm_event else random.randint(0, 1)
    substance_use = random.randint(0, 2) if mood_state == 'MANIC' else 0
    risky_behavior = random.randint(0, 1) if mood_state == 'MANIC' else 0
    
    # Appetite and impulse
    appetite = random.randint(3, 7)
    impulse_control = random.randint(4, 8)
    impulse_spending = random.randint(0, 1) if mood_state == 'MANIC' else 0
    impulse_food = random.randint(0, 1) if mood_state in ['DEPRESSED', 'MANIC'] else 0
    impulse_sex = random.randint(0, 1) if mood_state == 'MANIC' else 0
    impulse_drugs = random.randint(0, 1) if mood_state == 'MANIC' else 0
    impulse_alcohol = random.randint(0, 1) if mood_state in ['DEPRESSED', 'MANIC'] else 0
    
    # --- 2. Structure Data into JSONB Columns ---
    
    # sleep_data JSONB
    sleep_data = SleepData(
        sleep_hours=sleep_hours,
        sleep_quality=sleep_quality,
        sleep_disrupted=random.randint(0, 1),
        sleep_aids_used=random.randint(0, 1)
    ).model_dump()
    
    # mood_data JSONB
    mood_data = MoodData(
        energy_level=energy_level,
        depressed_mood=depressed_mood,
        anxiety_stress=anxiety_stress,
        activation=activation,
        elevation=elevation,
        social_connection=social_connection,
        contextual_stressors=contextual_stressors,
        social_rhythm_event=social_rhythm_event
    ).model_dump()
    
    # symptoms_data JSONB
    symptoms_data = SymptomsData(
        thought_speed=thought_speed,
        distractibility=distractibility,
        libido=libido,
        compulsion_episode=compulsion_episode,
        compulsion_intensity=compulsion_intensity,
        motivation=motivation,
        tasks_planned=tasks_planned,
        tasks_completed=tasks_completed
    ).model_dump()
    
    # risk_routine_data JSONB
    risk_routine_data = RiskRoutineData(
        suicidal_ideation=suicidal_ideation,
        suicide_risk=suicide_risk,
        self_harm=self_harm,
        routine_disruption=routine_disruption,
        substance_use=substance_use,
        risky_behavior=risky_behavior
    ).model_dump()
    
    # appetite_impulse_data JSONB
    appetite_impulse_data = AppetiteImpulseData(
        appetite=appetite,
        impulse_control=impulse_control,
        impulse_spending=impulse_spending,
        impulse_food=impulse_food,
        impulse_sex=impulse_sex,
        impulse_drugs=impulse_drugs,
        impulse_alcohol=impulse_alcohol
    ).model_dump()
    
    # meds_context_data JSONB
    meds_context_data = MedsContextData(
        medication_adherence=medication_adherence,
        medication_timing=medication_timing,
        medication_change_recent=medication_change_recent
    ).model_dump()
    
    # --- 3. Assemble Full Check-in Dict ---
    return {
        "user_id": user_id,
        "checkin_date": checkin_date.isoformat(),
        "sleep_data": sleep_data,
        "mood_data": mood_data,
        "symptoms_data": symptoms_data,
        "risk_routine_data": risk_routine_data,
        "appetite_impulse_data": appetite_impulse_data,
        "meds_context_data": meds_context_data
    }


def generate_user_checkin_history(
    user_id: str,
    num_checkins: int = 30,
    mood_pattern: str = 'stable',
    start_date: datetime = None
) -> List[Dict[str, Any]]:
    """
    Generate a history of check-ins for a user with specified mood pattern.
    
    Args:
        user_id: User UUID
        num_checkins: Number of check-ins to generate
        mood_pattern: 'stable' (mostly euthymic), 'cycling' (cycles every 7-14 days), or 'random'
        start_date: Optional start date (defaults to today - num_checkins days)
        
    Returns:
        List of check-in dictionaries
    """
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=num_checkins)
    
    checkins = []
    
    # Generate mood sequence based on pattern
    mood_sequence = []
    
    if mood_pattern == 'cycling':
        # Bipolar cycling: 7-14 day episodes
        episode_length = random.randint(7, 14)
        moods = ['EUTHYMIC', 'MANIC', 'DEPRESSED', 'MIXED']
        current_mood = random.choice(moods)
        
        for i in range(num_checkins):
            if i % episode_length == 0:
                current_mood = random.choice([m for m in moods if m != current_mood])
            mood_sequence.append(current_mood)
            
    elif mood_pattern == 'stable':
        # Mostly euthymic with occasional deviations
        for _ in range(num_checkins):
            mood_sequence.append(random.choices(
                ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
                weights=[0.8, 0.1, 0.05, 0.05]
            )[0])
            
    else:  # random
        for _ in range(num_checkins):
            mood_sequence.append(random.choices(
                ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
                weights=[0.5, 0.25, 0.15, 0.10]
            )[0])
    
    # Generate check-ins
    for i in range(num_checkins):
        checkin_date = start_date + timedelta(days=i)
        checkin = generate_realistic_checkin(
            user_id=user_id,
            checkin_date=checkin_date,
            mood_state=mood_sequence[i]
        )
        checkins.append(checkin)
    
    return checkins


async def generate_and_populate_data(
    supabase: AsyncClient,
    checkins_per_user: int = 30,
    mood_pattern: str = 'stable',
    num_users: Optional[int] = None,
    patients_count: Optional[int] = None,
    therapists_count: Optional[int] = None
) -> Dict[str, Any]:
    # Compatibilidade com parâmetros antigos e novos
    if patients_count is not None or therapists_count is not None:
        patients_count = patients_count or 0
        therapists_count = therapists_count or 0
    else:
        patients_count = num_users or 0
        therapists_count = 0

    total_users = patients_count + therapists_count
    logger.info(f"Iniciando geração de dados: {patients_count} pacientes + {therapists_count} terapeutas")

    all_checkins: List[Dict[str, Any]] = []
    user_ids: List[str] = []
    patients_created = 0
    therapists_created = 0

    try:
        # === PACIENTES ===
        for _ in range(patients_count):
            email = fake.unique.email()
            password = fake.password(length=20)

            # 1. Criar no Auth primeiro → Supabase gera o ID real
            auth_resp = await supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True
            })
            user_id = auth_resp.user.id

            # 2. Criar profile usando o ID real do Auth
            await supabase.table('profiles').insert({
                "id": user_id,
                "email": email,
                "role": "patient",
                "is_test_patient": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).execute()

            patients_created += 1
            user_ids.append(user_id)

            # 3. Gerar check-ins
            checkins = generate_user_checkin_history(
                user_id=user_id,
                num_checkins=checkins_per_user,
                mood_pattern=mood_pattern
            )
            all_checkins.extend(checkins)

        # === TERAPEUTAS ===
        for _ in range(therapists_count):
            email = fake.unique.email()
            password = fake.password(length=20)

            auth_resp = await supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True
            })
            user_id = auth_resp.user.id

            await supabase.table('profiles').insert({
                "id": user_id,
                "email": email,
                "role": "therapist",
                "is_test_patient": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).execute()

            therapists_created += 1
            user_ids.append(user_id)

        # === Inserir todos os check-ins de uma vez ===
        inserted_count = 0
        if all_checkins:
            resp = await supabase.table('check_ins').insert(all_checkins).execute()
            inserted_count = len(resp.data) if resp.data else 0

        return {
            "status": "success",
            "message": f"Gerados {patients_created} pacientes e {therapists_created} terapeutas com {inserted_count} check-ins",
            "statistics": {
                "patients_created": patients_created,
                "therapists_created": therapists_created,
                "total_checkins": inserted_count,
                "user_ids": user_ids,
                "users_created": total_users,
                "checkins_per_user": checkins_per_user,
                "mood_pattern": mood_pattern,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }

    except Exception as e:
        logger.exception("Falha crítica na geração de dados sintéticos")
        raise HTTPException(status_code=500, detail="Erro ao gerar dados sintéticos. Veja os logs do servidor.")
