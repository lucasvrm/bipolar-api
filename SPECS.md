Bipolar AI Engine - Expanded Analytics Platform
Visão Geral
A Bipolar AI Engine é uma plataforma completa de análise clínica e autoconhecimento para transtorno bipolar, expandida de um sistema simples de alerta de crise para uma solução abrangente com 10 análises preditivas diferentes.

Versão: 3.0
Framework: FastAPI
Modelos: LightGBM, Scikit-learn, SHAP, Lifelines

🎯 Funcionalidades Principais
Grupo I: Previsão Clínica
Previsão de Crise T+3 - Modelo original de predição de crise em 3 dias
Previsão de Crise T+7 - Predição estendida para 7 dias
Previsão de Transição de Estado - Classificação multi-classe (Estável, Depressivo, Maníaco, Misto)
Previsão de Comportamento Impulsivo - Risco de comportamentos impulsivos em 2 dias
Grupo II: Autoconhecimento
Análise de Causa-Raiz (SHAP) - Explicação das principais features que influenciam predições
Análise de Gatilhos Ambientais - Identificação de padrões e estressores correlacionados com crises
Clusterização de Estados de Humor - Identificação de padrões recorrentes de humor
Grupo III: Otimização de Tratamento
Previsão de Adesão à Medicação - Risco de não-adesão medicamentosa
Análise Causal de Medicação - Avaliação do impacto de mudanças medicamentosas
Otimização de Hábito Único - Correlação entre hábitos específicos e estabilidade do humor
Grupo IV: Engajamento
Previsão de Abandono do App - Análise de risco de churn baseada em métricas de engajamento
📁 Estrutura do Projeto
/bipolar-api
├── main.py                          # API principal com todos os endpoints
├── requirements.txt                 # Dependências do projeto
├── lightgbm_crisis_binary_v1.pkl   # Modelo LightGBM original
├── models/                          # Diretório para modelos adicionais
├── analysis/
│   ├── __init__.py
│   ├── clinical_prediction.py      # Módulo de previsões clínicas
│   ├── self_knowledge.py           # Módulo de autoconhecimento
│   ├── treatment_optimization.py   # Módulo de otimização de tratamento
│   └── engagement.py               # Módulo de engajamento
└── features/
    ├── __init__.py
    └── engineering.py              # Feature engineering
🚀 Instalação
# Clone o repositório
git clone https://github.com/lucasvrm/bipolar-api.git
cd bipolar-api

# Instale as dependências
pip install -r requirements.txt

# Execute o servidor
uvicorn main:app --reload
O servidor estará disponível em http://localhost:8000

📚 Documentação da API
Endpoints Disponíveis
Health Check
GET /
Retorna o status do servidor e dos módulos carregados.

Informações da API
GET /api/info
Retorna documentação completa de todos os endpoints disponíveis.

Grupo I: Previsão Clínica
1. Previsão de Crise T+3 (Original)
POST /predict
Com análise SHAP opcional:

POST /predict?include_shap=true
Request Body:

{
  "features": {
    "mood": 3.5,
    "energyLevel": 2.0,
    "hoursSlept": 4.5,
    "anxiety": 7.0,
    "activation": 8.0
  }
}
Response:

{
  "probability": 0.7234,
  "risk_level": "HIGH",
  "alert": true,
  "timeframe_days": 3,
  "features_processed": 65,
  "shap_analysis": {
    "top_contributors": [
      {
        "feature": "hoursSlept",
        "shap_value": 0.45,
        "feature_value": 4.5,
        "impact": "increases_risk"
      }
    ]
  }
}
2. Previsão de Crise T+7
POST /predict/crisis/7d
Request/Response: Similar ao endpoint /predict, mas com predição para 7 dias.

3. Previsão de Transição de Estado
POST /predict/state/3d
Response:

{
  "predicted_state": "MANIC",
  "probabilities": {
    "STABLE": 0.1,
    "DEPRESSIVE": 0.15,
    "MANIC": 0.65,
    "MIXED": 0.1
  },
  "confidence": 0.65,
  "timeframe_days": 3
}
4. Previsão de Comportamento Impulsivo
POST /predict/impulsive_behavior/2d
Response:

{
  "probability": 0.6234,
  "risk_level": "MODERATE",
  "alert": true,
  "timeframe_days": 2
}
Grupo II: Autoconhecimento
5. Análise de Gatilhos Ambientais
GET /patient/{patient_id}/triggers?history={json_history}
Exemplo de History (URL encoded):

[
  {
    "date": "2024-01-01",
    "contextualStressors": ["work_deadline", "sleep_deprivation"],
    "notes": "Feeling very stressed and anxious"
  }
]
Response:

{
  "patient_id": "patient_123",
  "triggers": [
    {
      "trigger": "work_deadline",
      "frequency": 8,
      "risk_level": "HIGH"
    }
  ],
  "patterns": {
    "most_common_stressor": "work_deadline",
    "note_sentiments": {
      "negative_sentiment_indicators": 15,
      "positive_sentiment_indicators": 3,
      "overall_tone": "NEGATIVE"
    }
  },
  "recommendations": [
    "Practice stress management techniques for work-related stress"
  ]
}
6. Clusterização de Estados de Humor
GET /patient/{patient_id}/mood_clusters?history={json_history}&n_clusters=4
Response:

{
  "patient_id": "patient_123",
  "clusters": [
    {
      "cluster_id": 0,
      "label": "Depressive State",
      "count": 15,
      "percentage": 50.0,
      "characteristics": {
        "mood": 3.2,
        "energy": 2.8,
        "activation": 2.5,
        "anxiety": 6.1,
        "irritability": 4.2
      }
    }
  ],
  "total_data_points": 30,
  "dominant_state": "Depressive State"
}
Grupo III: Otimização de Tratamento
7. Previsão de Adesão à Medicação
POST /predict/medication_adherence/3d
Response:

{
  "non_adherence_probability": 0.4523,
  "risk_level": "MODERATE",
  "alert": false,
  "timeframe_days": 3,
  "recommendations": [
    "Maintain consistent medication routine",
    "Track medication in app daily"
  ]
}
8. Análise Causal de Medicação
POST /analyze/medication_impact
Request Body:

{
  "patient_history": [
    {"date": "2024-01-01", "mood": 4.5},
    {"date": "2024-01-15", "mood": 6.0}
  ],
  "medication_change": {
    "medication": "Lithium",
    "index": 7
  }
}
Response:

{
  "medication": "Lithium",
  "average_treatment_effect": {
    "mood_stability_change": 0.532,
    "mood_level_change": 1.2,
    "interpretation": "significantly improved stability, elevated mood"
  },
  "statistical_significance": {
    "p_value": 0.0234,
    "significant": true
  },
  "before_period": {
    "mean_mood": 4.2,
    "mood_stability": 1.8,
    "days": 7
  },
  "after_period": {
    "mean_mood": 5.4,
    "mood_stability": 1.27,
    "days": 8
  }
}
9. Otimização de Hábito Único
GET /patient/{patient_id}/habit_optimization?habit=exerciseDurationMin&history={json_history}
Response:

{
  "patient_id": "patient_123",
  "habit": "exerciseDurationMin",
  "correlation_with_mood": 0.452,
  "statistical_significance": {
    "p_value": 0.0123,
    "significant": true
  },
  "optimal_range": "(30.0, 45.0]",
  "current_average": 22.5,
  "recommendation": "exerciseDurationMin in range (30.0, 45.0] associated with best mood stability. Higher values correlate with improved mood.",
  "data_points": 28
}
Grupo IV: Engajamento
10. Previsão de Risco de Churn
GET /patient/{patient_id}/churn_risk?history={json_history}
Response:

{
  "patient_id": "patient_123",
  "churn_risk_level": "MODERATE",
  "churn_probability_30d": 0.4523,
  "engagement_metrics": {
    "total_days_tracked": 22,
    "consistency_score": 0.733,
    "average_completeness": 0.68,
    "engagement_trend": -0.05,
    "notes_engagement_rate": 0.45,
    "last_entry_days_ago": 0
  },
  "risk_factors": [
    "Moderate tracking consistency",
    "Slight decline in engagement"
  ],
  "recommendations": [
    "Enable push notifications for daily check-ins",
    "Send re-engagement campaign with new insights"
  ]
}
🔧 Estrutura de Dados
Features Esperadas (65 features no total)
As principais features incluem:

Dados demográficos: sex, diagnosis_state_ground_truth
Sono: hoursSlept, sleepQuality, sleepHygiene, perceivedSleepNeed, hasNapped, nappingDurationMin
Humor e Emoções: mood, anxiety, irritability, energyLevel, activation
Comportamento: libido, focusQuality, socialInteractionQuality, socialWithdrawal
Hábitos: caffeineDoses, exerciseDurationMin, medicationAdherence
Features Temporais: sleep_zscore_30d, mood_volatility_30d, anxiety_trend_30d, etc.
🧠 Modelos de Machine Learning
Modelos Implementados
LightGBM Classifier - Previsão de crise binária (existente)
Multi-class Classifier - Transição de estados (heurística/modelo futuro)
Binary Classifiers - Comportamento impulsivo e adesão medicamentosa
Cox Proportional Hazards - Análise de sobrevivência para churn
K-Means Clustering - Clusterização de estados de humor
Fallbacks Inteligentes
Quando modelos específicos não estão treinados, o sistema usa:

Predições baseadas em heurísticas usando regras clínicas
Modelos existentes com ajustes de threshold
Análises estatísticas simplificadas
🔬 Tecnologias Utilizadas
FastAPI - Framework web de alta performance
LightGBM - Gradient boosting para classificação
Scikit-learn - Algoritmos de ML (clustering, regression)
SHAP - Explicabilidade de modelos
Lifelines - Análise de sobrevivência
NLTK - Processamento de linguagem natural
Pandas/NumPy - Manipulação de dados
SciPy - Análises estatísticas
📊 Exemplo de Uso Completo
import requests
import json

# Base URL
BASE_URL = "http://localhost:8000"

# 1. Previsão de crise com SHAP
response = requests.post(
    f"{BASE_URL}/predict?include_shap=true",
    json={
        "features": {
            "mood": 3.0,
            "energyLevel": 2.0,
            "hoursSlept": 4.0,
            "anxiety": 8.0
        }
    }
)
print("Crisis prediction:", response.json())

# 2. Análise de gatilhos
patient_history = [
    {"contextualStressors": ["work_stress"], "mood": 4.0},
    {"contextualStressors": ["sleep_deprivation"], "mood": 3.0}
]
response = requests.get(
    f"{BASE_URL}/patient/patient_123/triggers",
    params={"history": json.dumps(patient_history)}
)
print("Triggers:", response.json())

# 3. Otimização de exercício
response = requests.get(
    f"{BASE_URL}/patient/patient_123/habit_optimization",
    params={
        "habit": "exerciseDurationMin",
        "history": json.dumps(patient_history)
    }
)
print("Habit optimization:", response.json())
🔒 Segurança e CORS
A API está configurada com CORS para aceitar requisições de:

https://previso-fe.vercel.app
http://localhost:3000
http://localhost:5173
Para adicionar novas origens, edite o array origins em main.py.

🚦 Status Codes
200 - Sucesso
400 - Erro de validação ou processamento
500 - Erro interno do servidor
📈 Roadmap Futuro
 Treinar modelos específicos para T+7, estados, comportamento impulsivo
 Implementar propensity score matching completo para análise causal
 Adicionar suporte para múltiplos idiomas em análise de notas
 Implementar sistema de feedback para melhorar modelos
 Adicionar endpoints de retreinamento de modelos
 Dashboard de visualização de insights
🤝 Contribuindo
Contribuições são bem-vindas! Para contribuir:

Fork o projeto
Crie uma branch para sua feature (git checkout -b feature/AmazingFeature)
Commit suas mudanças (git commit -m 'Add some AmazingFeature')
Push para a branch (git push origin feature/AmazingFeature)
Abra um Pull Request
📝 Licença
Este projeto está sob licença MIT. Veja o arquivo LICENSE para mais detalhes.

👥 Autores
Lucas VRM - Desenvolvimento inicial
🙏 Agradecimentos
Equipe de pesquisa em transtorno bipolar
Comunidade de desenvolvedores FastAPI
Contribuidores do projeto
