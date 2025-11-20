# feature_engineering.py
import pandas as pd
import numpy as np

# Lista completa de todas as features que os modelos esperam (66 features)
EXPECTED_FEATURES = [
    'sex', 'diagnosis_state_ground_truth', 'hoursSlept', 'sleepQuality',
    'sleepHygiene', 'perceivedSleepNeed', 'hasNapped', 'nappingDurationMin',
    'caffeineDoses', 'energyLevel', 'distractibility', 'motivationToStart',
    'thoughtSpeed', 'libido', 'tasksPlanned', 'tasksCompleted',
    'depressedMood', 'anxietyStress', 'activation', 'elevation',
    'medicationAdherence', 'medicationTiming', 'substanceUsage', 'substanceUnits',
    'socialRhythmEvent', 'medicationChangeRecent', 'contextualStressors', 'socialConnection',
    'exerciseDurationMin', 'exerciseFeeling', 'memoryConcentration', 'ruminationAxis',
    'dietTracking', 'generalAppetite', 'skipMeals', 'compulsionEpisode',
    'compulsionIntensity', 'sexualRiskBehavior', 'day_of_year', 'is_weekend',
    'impulse_daily_count', 'bedTime_float_sin', 'bedTime_float_cos', 'wakeTime_float_sin',
    'wakeTime_float_cos', 'day_of_year_sin', 'day_of_year_cos', 'sleep_mean_7d',
    'sleep_mean_30d', 'sleep_std_30d', 'sleep_debt_3d', 'perceived_need_trend_7d',
    'energy_mean_7d', 'energy_mean_30d', 'mixed_state_index_3d', 'mood_volatility_30d',
    'srm_7d', 'impulse_count_60d', 'social_withdrawal_7d', 'sleep_zscore_30d',
    'energy_trend_ratio', 'hoursSlept_t-1', 'hoursSlept_t-2', 'energyLevel_t-1',
    'energyLevel_t-2', 'diagnosis_state_ground_truth_t-1',
]

# Mapeamento de features categóricas com seus valores possíveis
# Extraído diretamente do modelo treinado
CATEGORICAL_FEATURES = {
    'sex': ['F', 'M'],
    'diagnosis_state_ground_truth': ['DEPRESSED', 'EUTHYMIC', 'MANIC', 'MIXED'],
    'hoursSlept': ['Full', 'None', 'Partial'],
    'sleepQuality': ['OnTime'],
    'sleepHygiene': ['DEPRESSED', 'EUTHYMIC', 'MANIC', 'MIXED'],
}

def create_features_for_prediction(input_features: dict) -> pd.DataFrame:
    """
    Cria um DataFrame com a estrutura completa que o modelo espera,
    preenche com valores padrão e atualiza com os dados recebidos.
    
    Esta função garante que:
    1. Todas as 66 features esperadas estejam presentes
    2. Features categóricas sejam do tipo 'category' com os valores corretos
    3. Features numéricas sejam do tipo 'float32'
    4. A ordem das colunas esteja correta
    """
    # 1. Crie um dicionário com todas as colunas esperadas
    full_feature_set = {}
    
    for feature in EXPECTED_FEATURES:
        if feature in CATEGORICAL_FEATURES:
            # Para features categóricas, use o primeiro valor como padrão
            default_value = CATEGORICAL_FEATURES[feature][0]
        else:
            # Para features numéricas, use 0.0 como padrão
            default_value = 0.0
        
        full_feature_set[feature] = default_value

    # 2. Atualize este dicionário com os valores que recebemos do request
    for key, value in input_features.items():
        if key in full_feature_set:
            full_feature_set[key] = value

    # 3. Crie um DataFrame a partir do dicionário completo
    df = pd.DataFrame([full_feature_set])

    # 4. Converta features categóricas para o tipo 'category' com as categorias corretas
    for col_name, categories in CATEGORICAL_FEATURES.items():
        if col_name in df.columns:
            # Se o valor não está nas categorias esperadas, use o primeiro valor
            current_value = df[col_name].iloc[0]
            if current_value not in categories:
                df[col_name] = categories[0]
            # Converta para categorical com as categorias definidas
            df[col_name] = pd.Categorical(df[col_name], categories=categories)

    # 5. Converta todas as outras colunas para float32
    for col in df.columns:
        if col not in CATEGORICAL_FEATURES:
            df[col] = df[col].astype(np.float32)

    # 6. Garanta que a ordem das colunas está correta
    return df[EXPECTED_FEATURES]
