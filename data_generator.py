"""
Data generator module for creating synthetic realistic bipolar disorder check-in data.
This module provides functionality to generate synthetic patient data with realistic
patterns for bipolar disorder monitoring, mapped correctly to the database JSONB schema.
"""
import random
import uuid
from datetime import datetime, timedelta, timezone
from faker import Faker
from typing import List, Dict, Any, Optional
from supabase import AsyncClient, create_client
import logging
from fastapi import HTTPException
from postgrest.exceptions import APIError
from api.schemas.checkin_jsonb import (
    SleepData,
    MoodData,
    SymptomsData,
    RiskRoutineData,
    AppetiteImpulseData,
    MedsContextData
)

fake = Faker('pt_BR')
logger = logging.getLogger("bipolar-api.data_generator")
logger.setLevel(logging.DEBUG)


def generate_realistic_checkin(
    user_id: str,
    checkin_date: datetime,
    mood_state: str = None
) -> Dict[str, Any]:
    if mood_state is None:
        mood_state = random.choices(
            ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
            weights=[0.5, 0.25, 0.15, 0.10]
        )[0]
   
    if mood_state == 'MANIC':
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
        tasks_completed = random.randint(1, tasks_planned)
       
    elif mood_state == 'DEPRESSED':
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

    medication_adherence = 1 if (mood_state == 'EUTHYMIC' or random.random() > 0.3) else 0
    medication_timing = random.randint(0, 1) if medication_adherence else 0
    medication_change_recent = 1 if random.random() < 0.05 else 0
   
    social_connection = max(0, min(10, 10 - anxiety_stress // 2 + random.randint(-2, 2)))
    contextual_stressors = random.randint(0, 1)
    social_rhythm_event = 1 if random.random() < 0.15 else 0
   
    suicidal_ideation = random.randint(0, 3) if mood_state == 'DEPRESSED' else 0
    suicide_risk = random.randint(0, 2) if suicidal_ideation > 0 else 0
    self_harm = random.randint(0, 1) if mood_state in ['DEPRESSED', 'MIXED'] else 0
    routine_disruption = 1 if social_rhythm_event else random.randint(0, 1)
    substance_use = random.randint(0, 1) if mood_state == 'MANIC' else 0
    risky_behavior = random.randint(0, 1) if mood_state == 'MANIC' else 0
   
    appetite = random.randint(3, 7)
    impulse_control = random.randint(4, 8)
    impulse_spending = random.randint(0, 1) if mood_state == 'MANIC' else 0
    impulse_food = random.randint(0, 1) if mood_state in ['DEPRESSED', 'MANIC'] else 0
    impulse_sex = random.randint(0, 1) if mood_state == 'MANIC' else 0
    impulse_drugs = random.randint(0, 1) if mood_state == 'MANIC' else 0
    impulse_alcohol = random.randint(0, 1) if mood_state in ['DEPRESSED', 'MANIC'] else 0
   
    sleep_data = SleepData(
        hoursSlept=sleep_hours,
        sleepQuality=sleep_quality,
        perceivedSleepNeed=round(random.uniform(6.0, 9.0), 1),
        sleepHygiene=random.randint(3, 8),
        hasNapped=random.randint(0, 1),
        nappingDurationMin=random.randint(0, 90) if random.random() < 0.3 else 0
    ).model_dump()
   
    mood_data = MoodData(
        energyLevel=energy_level,
        depressedMood=depressed_mood,
        anxietyStress=anxiety_stress,
        elevation=elevation,
        activation=activation,
        motivationToStart=motivation
    ).model_dump()
   
    symptoms_data = SymptomsData(
        thoughtSpeed=thought_speed,
        distractibility=distractibility,
        memoryConcentration=random.randint(3, 8),
        ruminationAxis=random.randint(2, 7)
    ).model_dump()
   
    risk_routine_data = RiskRoutineData(
        socialConnection=social_connection,
        socialRhythmEvent=social_rhythm_event,
        exerciseDurationMin=random.randint(0, 90),
        exerciseFeeling=random.randint(3, 8),
        sexualRiskBehavior=risky_behavior,
        tasksPlanned=tasks_planned,
        tasksCompleted=tasks_completed
    ).model_dump()
   
    appetite_impulse_data = AppetiteImpulseData(
        generalAppetite=appetite,
        dietTracking=random.randint(0, 1),
        skipMeals=random.randint(0, 1) if mood_state == 'DEPRESSED' else 0,
        compulsionEpisode=compulsion_episode,
        compulsionIntensity=compulsion_intensity,
        substanceUsage=substance_use,
        substanceUnits=random.randint(0, 5) if substance_use else 0,
        caffeineDoses=random.randint(0, 4),
        libido=libido
    ).model_dump()
   
    meds_context_data = MedsContextData(
        medicationAdherence=medication_adherence,
        medicationTiming=medication_timing,
        medicationChangeRecent=medication_change_recent,
        contextualStressors=contextual_stressors
    ).model_dump()
   
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
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=num_checkins)
   
    checkins = []
   
    mood_sequence = []
   
    if mood_pattern == 'cycling':
        episode_length = random.randint(7, 14)
        moods = ['EUTHYMIC', 'MANIC', 'DEPRESSED', 'MIXED']
        current_mood = random.choice(moods)
       
        for i in range(num_checkins):
            if i % episode_length == 0:
                current_mood = random.choice([m for m in moods if m != current_mood])
            mood_sequence.append(current_mood)
           
    elif mood_pattern == 'stable':
        for _ in range(num_checkins):
            mood_sequence.append(random.choices(
                ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
                weights=[0.8, 0.1, 0.05, 0.05]
            )[0])
    else:
        for _ in range(num_checkins):
            mood_sequence.append(random.choices(
                ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
                weights=[0.5, 0.25, 0.15, 0.10]
            )[0])
   
    for i in range(num_checkins):
        checkin_date = start_date + timedelta(days=i)
        checkin = generate_realistic_checkin(
            user_id=user_id,
            checkin_date=checkin_date,
            mood_state=mood_sequence[i]
        )
        checkins.append(checkin)
   
    return checkins


async def create_user_with_retry(
    supabase: AsyncClient,
    role: str,
    max_retries: int = 3
) -> tuple[str, str, str]:
    for attempt in range(max_retries):
        try:
            email = fake.unique.email()
            password = fake.password(length=20)
           
            logger.debug(f"Tentativa {attempt + 1}/{max_retries}: criando {role} → {email}")
           
            auth_resp = await supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True
            })
            user_id = auth_resp.user.id
           
            logger.debug(f"Usuário auth criado: {user_id}")
           
            await supabase.table('profiles').insert({
                "id": user_id,
                "email": email,
                "role": role,
                "is_test_patient": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).execute()
           
            logger.info(f"✓ {role} criado → {user_id} ({email})")
            return user_id, email, password
           
        except APIError as e:
            error_msg = str(e).lower()
            if "invalid api key" in error_msg:
                logger.error("FALHA CRÍTICA: Supabase client criado com anon key. Use service_role key!")
                raise HTTPException(
                    status_code=500,
                    detail="Invalid API key – cliente Supabase deve usar SUPABASE_SERVICE_KEY"
                )
            if "duplicate" in error_msg or "unique" in error_msg:
                logger.warning(f"Duplicata na tentativa {attempt + 1}, tentando novamente...")
                fake.unique.clear()
                continue
           
            logger.error(f"APIError: {e}")
            raise HTTPException(status_code=500, detail=str(e))
           
        except Exception as e:
            logger.error(f"Erro inesperado: {e}", exc_info=True)
            if attempt == max_retries - 1:
                raise HTTPException(status_code=500, detail=f"Erro ao criar usuário: {str(e)}")
   
    raise HTTPException(status_code=500, detail="Falha após todas as tentativas (duplicate key)")


async def generate_checkins_for_user(
    supabase: AsyncClient,
    user_id: str,
    num_checkins: int,
    mood_pattern: str
) -> int:
    logger.debug(f"Gerando {num_checkins} check-ins para {user_id} ({mood_pattern})")
    checkins = generate_user_checkin_history(user_id, num_checkins, mood_pattern)
   
    inserted = 0
    for i, checkin in enumerate(checkins):
        try:
            await supabase.table('check_ins').insert(checkin).execute()
            inserted += 1
            if (i + 1) % 10 == 0:
                logger.debug(f"{i+1}/{num_checkins} inseridos")
        except Exception as e:
            logger.error(f"Check-in {i+1} falhou: {e}")
   
    return inserted


async def generate_and_populate_data(
    supabase: AsyncClient,
    checkins_per_user: int = 30,
    mood_pattern: str = 'stable',
    num_users: Optional[int] = None,
    patients_count: Optional[int] = None,
    therapists_count: Optional[int] = None,
    days_history: Optional[int] = None
) -> Dict[str, Any]:
    if days_history is not None:
        checkins_per_user = days_history
   
    patients_count = patients_count or num_users or 0
    therapists_count = therapists_count or 0
   
    logger.info(f"Iniciando geração: {patients_count} pacientes + {therapists_count} terapeutas, {checkins_per_user} check-ins cada")
   
    total_checkins = 0
    user_ids = []
   
    for i in range(patients_count):
        user_id, email, _ = await create_user_with_retry(supabase, "patient")
        user_ids.append(user_id)
        checkins = await generate_checkins_for_user(supabase, user_id, checkins_per_user, mood_pattern)
        total_checkins += checkins
        logger.info(f"Paciente {i+1}/{patients_count} criado – {checkins} check-ins")
   
    for i in range(therapists_count):
        user_id, email, _ = await create_user_with_retry(supabase, "therapist")
        user_ids.append(user_id)
        logger.info(f"Terapeuta {i+1}/{therapists_count} criado")
   
    return {
        "status": "success",
        "statistics": {
            "patients_created": patients_count,
            "therapists_created": therapists_count,
            "users_created": patients_count + therapists_count,
            "total_checkins": total_checkins,
            "checkins_per_user": checkins_per_user,
            "mood_pattern": mood_pattern,
            "user_ids": user_ids
        }
    }
