# Bipolar AI Engine - Expanded Analytics Platform

## Visão Geral

A **Bipolar AI Engine** é uma plataforma completa de análise clínica e autoconhecimento para transtorno bipolar, expandida de um sistema simples de alerta de crise para uma solução abrangente com 10 análises preditivas diferentes.

**Versão:** 3.0  
**Framework:** FastAPI  
**Modelos:** LightGBM, Scikit-learn, SHAP, Lifelines

## 🎯 Funcionalidades Principais

### Grupo I: Previsão Clínica
1. **Previsão de Crise T+3** - Modelo original de predição de crise em 3 dias
2. **Previsão de Crise T+7** - Predição estendida para 7 dias
3. **Previsão de Transição de Estado** - Classificação multi-classe (Estável, Depressivo, Maníaco, Misto)
4. **Previsão de Comportamento Impulsivo** - Risco de comportamentos impulsivos em 2 dias

### Grupo II: Autoconhecimento
5. **Análise de Causa-Raiz (SHAP)** - Explicação das principais features que influenciam predições
6. **Análise de Gatilhos Ambientais** - Identificação de padrões e estressores correlacionados com crises
7. **Clusterização de Estados de Humor** - Identificação de padrões recorrentes de humor

### Grupo III: Otimização de Tratamento
8. **Previsão de Adesão à Medicação** - Risco de não-adesão medicamentosa
9. **Análise Causal de Medicação** - Avaliação do impacto de mudanças medicamentosas
10. **Otimização de Hábito Único** - Correlação entre hábitos específicos e estabilidade do humor

### Grupo IV: Engajamento
11. **Previsão de Abandono do App** - Análise de risco de churn baseada em métricas de engajamento

## 📁 Estrutura do Projeto

```
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
```

## 🚀 Instalação

```bash
# Clone o repositório
git clone https://github.com/lucasvrm/bipolar-api.git
cd bipolar-api

# Instale as dependências
pip install -r requirements.txt

# Configure as variáveis de ambiente
cp .env.example .env
# Edite o arquivo .env com suas credenciais do Supabase
# SUPABASE_URL: URL do seu projeto Supabase (https://app.supabase.com)
# SUPABASE_SERVICE_KEY: Service role key do seu projeto

# Execute o servidor
uvicorn main:app --reload
```

O servidor estará disponível em `http://localhost:8000`

### Configuração de Variáveis de Ambiente

O projeto requer as seguintes variáveis de ambiente:

- `SUPABASE_URL`: URL do projeto Supabase
- `SUPABASE_SERVICE_KEY`: Service role key para acesso ao banco de dados

**Variáveis Opcionais (Rate Limiting):**

- `RATE_LIMIT_DEFAULT`: Limite padrão para todos os endpoints (default: `60/minute`)
- `RATE_LIMIT_PREDICTIONS`: Limite para endpoints de predições (default: `10/minute`)
- `RATE_LIMIT_DATA_ACCESS`: Limite para endpoints de acesso a dados (default: `30/minute`)
- `RATE_LIMIT_STORAGE_URI`: URI do storage para rate limiting (default: `memory://`, use Redis em produção: `redis://host:port/db`)

**Importante:** Nunca commite o arquivo `.env` com credenciais reais. Use o arquivo `.env.example` como template.

## 🛡️ Rate Limiting

A API implementa rate limiting para prevenir abuso e garantir uso justo dos recursos. Por padrão:

- **Endpoints de Predições** (`/data/predictions/*`, `/data/prediction_of_day/*`): 10 requisições por minuto por usuário
- **Endpoints de Dados** (`/data/latest_checkin/*`): 30 requisições por minuto por usuário
- **Outros Endpoints**: 60 requisições por minuto por usuário

Quando o limite é excedido, a API retorna HTTP 429 (Too Many Requests) com cabeçalho `Retry-After` indicando quando tentar novamente.

**Exemplo de Resposta de Rate Limit:**
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please slow down and try again later.",
  "detail": "Rate limit exceeded",
  "retry_after": 60
}
```

## 📚 Documentação da API

### Endpoints Disponíveis

#### Health Check
```http
GET /
```
Retorna o status do servidor e dos módulos carregados.

#### Informações da API
```http
GET /api/info
```
Retorna documentação completa de todos os endpoints disponíveis.

---

### Multi-Type Predictions Endpoint

#### GET /data/predictions/{user_id}

Endpoint que retorna predições multi-tipo para análise de transtorno bipolar.

**Tipos de Predições Suportadas:**
1. **mood_state** - Estado de humor previsto (Eutimia, Depressão, Mania, Estado Misto)
2. **relapse_risk** - Probabilidade de recorrência de episódio significativo
3. **suicidality_risk** - Risco suicida (com disclaimer e recursos de apoio)
4. **medication_adherence_risk** - Risco de baixa adesão medicamentosa
5. **sleep_disturbance_risk** - Risco de perturbação do sono

**Query Parameters:**
- `types` (opcional): Lista separada por vírgulas de tipos de predição. Default: todos os 5 tipos.
  - Exemplo: `types=mood_state,relapse_risk`
- `window_days` (opcional): Janela temporal em dias (1-30). Default: 3.
- `limit_checkins` (opcional): Número de check-ins recentes para análise individual (0-10). Default: 0.

**Exemplo de Request:**
```bash
# Todas as predições com configuração padrão
curl "http://localhost:8000/data/predictions/{user_id}"

# Apenas mood_state e relapse_risk com janela de 7 dias
curl "http://localhost:8000/data/predictions/{user_id}?types=mood_state,relapse_risk&window_days=7"

# Com análise por check-in individual
curl "http://localhost:8000/data/predictions/{user_id}?limit_checkins=3"
```

**Response (200 OK):**
```json
{
  "user_id": "uuid-string",
  "window_days": 3,
  "generated_at": "2024-01-15T10:30:00Z",
  "predictions": [
    {
      "type": "mood_state",
      "label": "Eutimia",
      "probability": 0.61,
      "details": {
        "class_probs": {
          "Eutimia": 0.61,
          "Depressão": 0.20,
          "Mania": 0.10,
          "Estado Misto": 0.09
        }
      },
      "model_version": "lgbm_multiclass_v1",
      "explanation": "SHAP top features: hoursSlept=6.5 (impact: 0.234), energyLevel=5 (impact: 0.123), depressedMood=4 (impact: -0.089)",
      "source": "aggregated_last_checkin"
    },
    {
      "type": "suicidality_risk",
      "label": "Risco baixo",
      "probability": 0.23,
      "details": {},
      "model_version": "heuristic_v1",
      "explanation": "Based on mood and distress indicators. SEEK PROFESSIONAL HELP.",
      "source": "aggregated_last_checkin",
      "sensitive": true,
      "disclaimer": "Esta predição NÃO substitui avaliação clínica profissional. Se você está pensando em suicídio, procure ajuda imediatamente.",
      "resources": {
        "CVV": "188 (24h, gratuito)",
        "CAPS": "Centros de Atenção Psicossocial",
        "emergency": "SAMU 192 ou UPA/Emergência hospitalar"
      }
    }
  ],
  "per_checkin": [
    {
      "checkin_id": "checkin-uuid",
      "checkin_date": "2024-01-15T10:30:00Z",
      "predictions": [...]
    }
  ]
}
```

**Caso sem dados (usuário sem check-ins):**
```json
{
  "user_id": "uuid-string",
  "window_days": 3,
  "generated_at": "2024-01-15T10:30:00Z",
  "predictions": [
    {
      "type": "mood_state",
      "label": "Dados insuficientes",
      "probability": 0.0,
      "details": {},
      "model_version": null,
      "explanation": "No check-in data available for this user",
      "source": "aggregated_last_checkin"
    }
  ]
}
```

**Códigos de Status:**
- `200 OK` - Predições geradas com sucesso
- `400 Bad Request` - Parâmetros inválidos (tipos desconhecidos)
- `500 Internal Server Error` - Erro ao processar predições ou variáveis de ambiente não configuradas

**Notas Importantes:**
- O endpoint valida a presença de `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` e retorna erro 500 se ausentes
- Predições de `suicidality_risk` incluem disclaimer e recursos de emergência
- Logs são gerados para facilitar debug no Render
- Quando modelos específicos não estão disponíveis, heurísticas clínicas são usadas como fallback

---

### Grupo I: Previsão Clínica

#### 1. Previsão de Crise T+3 (Original)
```http
POST /predict
```

**Com análise SHAP opcional:**
```http
POST /predict?include_shap=true
```

**Request Body:**
```json
{
  "features": {
    "mood": 3.5,
    "energyLevel": 2.0,
    "hoursSlept": 4.5,
    "anxiety": 7.0,
    "activation": 8.0
  }
}
```

**Response:**
```json
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
```

#### 2. Previsão de Crise T+7
```http
POST /predict/crisis/7d
```

**Request/Response:** Similar ao endpoint `/predict`, mas com predição para 7 dias.

#### 3. Previsão de Transição de Estado
```http
POST /predict/state/3d
```

**Response:**
```json
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
```

#### 4. Previsão de Comportamento Impulsivo
```http
POST /predict/impulsive_behavior/2d
```

**Response:**
```json
{
  "probability": 0.6234,
  "risk_level": "MODERATE",
  "alert": true,
  "timeframe_days": 2
}
```

---

### Grupo II: Autoconhecimento

#### 5. Análise de Gatilhos Ambientais
```http
GET /patient/{patient_id}/triggers?history={json_history}
```

**Exemplo de History (URL encoded):**
```json
[
  {
    "date": "2024-01-01",
    "contextualStressors": ["work_deadline", "sleep_deprivation"],
    "notes": "Feeling very stressed and anxious"
  }
]
```

**Response:**
```json
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
```

#### 6. Clusterização de Estados de Humor
```http
GET /patient/{patient_id}/mood_clusters?history={json_history}&n_clusters=4
```

**Response:**
```json
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
```

---

### Grupo III: Otimização de Tratamento

#### 7. Previsão de Adesão à Medicação
```http
POST /predict/medication_adherence/3d
```

**Response:**
```json
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
```

#### 8. Análise Causal de Medicação
```http
POST /analyze/medication_impact
```

**Request Body:**
```json
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
```

**Response:**
```json
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
```

#### 9. Otimização de Hábito Único
```http
GET /patient/{patient_id}/habit_optimization?habit=exerciseDurationMin&history={json_history}
```

**Response:**
```json
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
```

---

### Grupo IV: Engajamento

#### 10. Previsão de Risco de Churn
```http
GET /patient/{patient_id}/churn_risk?history={json_history}
```

**Response:**
```json
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
```

---

## 🔧 Estrutura de Dados

### Features Esperadas (65 features no total)

As principais features incluem:
- **Dados demográficos:** `sex`, `diagnosis_state_ground_truth`
- **Sono:** `hoursSlept`, `sleepQuality`, `sleepHygiene`, `perceivedSleepNeed`, `hasNapped`, `nappingDurationMin`
- **Humor e Emoções:** `mood`, `anxiety`, `irritability`, `energyLevel`, `activation`
- **Comportamento:** `libido`, `focusQuality`, `socialInteractionQuality`, `socialWithdrawal`
- **Hábitos:** `caffeineDoses`, `exerciseDurationMin`, `medicationAdherence`
- **Features Temporais:** `sleep_zscore_30d`, `mood_volatility_30d`, `anxiety_trend_30d`, etc.

## 🧠 Modelos de Machine Learning

### Modelos Implementados
1. **LightGBM Classifier** - Previsão de crise binária (existente)
2. **Multi-class Classifier** - Transição de estados (heurística/modelo futuro)
3. **Binary Classifiers** - Comportamento impulsivo e adesão medicamentosa
4. **Cox Proportional Hazards** - Análise de sobrevivência para churn
5. **K-Means Clustering** - Clusterização de estados de humor

### Fallbacks Inteligentes
Quando modelos específicos não estão treinados, o sistema usa:
- Predições baseadas em heurísticas usando regras clínicas
- Modelos existentes com ajustes de threshold
- Análises estatísticas simplificadas

## 🔬 Tecnologias Utilizadas

- **FastAPI** - Framework web de alta performance
- **LightGBM** - Gradient boosting para classificação
- **Scikit-learn** - Algoritmos de ML (clustering, regression)
- **SHAP** - Explicabilidade de modelos
- **Lifelines** - Análise de sobrevivência
- **NLTK** - Processamento de linguagem natural
- **Pandas/NumPy** - Manipulação de dados
- **SciPy** - Análises estatísticas

## 📊 Exemplo de Uso Completo

```python
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
```

## 🔒 Segurança e CORS

A API está configurada com CORS para aceitar requisições de:
- `https://previso-fe.vercel.app`
- `http://localhost:3000`
- `http://localhost:5173`

Para adicionar novas origens, edite o array `origins` em `main.py`.

## 🚦 Status Codes

- `200` - Sucesso
- `400` - Erro de validação ou processamento
- `500` - Erro interno do servidor

## 📈 Roadmap Futuro

- [ ] Treinar modelos específicos para T+7, estados, comportamento impulsivo
- [ ] Implementar propensity score matching completo para análise causal
- [ ] Adicionar suporte para múltiplos idiomas em análise de notas
- [ ] Implementar sistema de feedback para melhorar modelos
- [ ] Adicionar endpoints de retreinamento de modelos
- [ ] Dashboard de visualização de insights

## 🤝 Contribuindo

Contribuições são bem-vindas! Para contribuir:

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📝 Licença

Este projeto está sob licença MIT. Veja o arquivo LICENSE para mais detalhes.

## 👥 Autores

- **Lucas VRM** - Desenvolvimento inicial

## 🙏 Agradecimentos

- Equipe de pesquisa em transtorno bipolar
- Comunidade de desenvolvedores FastAPI
- Contribuidores do projeto

---

**Nota:** Esta é uma plataforma de análise clínica e não substitui aconselhamento médico profissional. Sempre consulte profissionais de saúde qualificados para diagnóstico e tratamento.
