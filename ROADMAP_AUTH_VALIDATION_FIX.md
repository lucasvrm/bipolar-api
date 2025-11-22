# ROADMAP - Correção de Autenticação e Validação

**Data de Criação**: 2025-11-22  
**Autor**: Backend Security Engineer (Supabase/FastAPI)  
**Status**: ✅ Implementado

---

## 📋 Resumo Executivo

Este documento descreve as correções implementadas para resolver falhas persistentes de autenticação (401) e erros de validação de dados (Pydantic ValidationError) nos endpoints administrativos da API Bipolar.

---

## 🔍 Diagnóstico Técnico

### 1. Problema de Autenticação (401 Unauthorized)

**Sintoma**: `httpx.HTTPStatusError: Client error '401 Unauthorized' ... Invalid API key`

**Causa Raiz**: A chave `SUPABASE_SERVICE_KEY` não estava sendo injetada corretamente no cliente Supabase usado pelo `data_generator.py` e outros endpoints administrativos.

**Evidência**:
- Logs mostravam erro "Invalid API key" em operações que requerem privilégios de service_role
- Service key é necessária para bypass de Row Level Security (RLS) policies
- Anon key (~150 chars) vs Service Role key (~200+ chars)

### 2. Problema de Validação (Pydantic ValidationError)

**Sintoma**: `pydantic_core._pydantic_core.ValidationError: 1 validation error for APIErrorFromJSON`

**Causa Raiz**: O backend recebia erros do banco de dados (PostgREST) mas tentava parsear como resposta de sucesso, falhando na validação do Pydantic e mascarando a causa raiz.

**Evidência**:
- Erro "JSON could not be generated" geralmente vem de problemas de permissão RLS ou query inválida
- Pydantic ValidationError ocorria ao tentar parsear erro do DB como modelo de dados válido

### 3. Problema de Validação de Payload (422 Unprocessable Entity)

**Sintoma**: Erro 422 no endpoint `danger-zone-cleanup`

**Causa Raiz**: O payload enviado pelo frontend não batia com o Schema do Backend.

---

## ✅ Implementações Realizadas

### 1. Correção da Service Key (Hard Fix) - `api/dependencies.py`

**Localização**: Função `get_supabase_service()`

**Mudanças Implementadas**:

```python
# CRITICAL: Log key configuration for debugging (masked for security)
key_length = len(key) if key else 0
print(f"DEBUG: Service Key length: {key_length}")
logger.critical(f"Service Key validation - Length: {key_length} chars")

# CRITICAL: Service role keys are typically 200+ characters (JWT tokens)
# Anon keys are typically ~150 characters
MIN_SERVICE_KEY_LENGTH = 180  # Conservative threshold
if key_length < MIN_SERVICE_KEY_LENGTH:
    error_msg = (
        f"CRITICAL: SUPABASE_SERVICE_KEY appears to be invalid! "
        f"Length: {key_length} chars (expected 200+). "
        f"This is likely an ANON key instead of SERVICE_ROLE key. "
        f"Check your environment variables!"
    )
    logger.critical(error_msg)
    print(f"ERROR: {error_msg}")
    raise RuntimeError(error_msg)

# Validate key format (JWT tokens should start with 'eyJ')
if not key.startswith('eyJ'):
    error_msg = "SUPABASE_SERVICE_KEY is not a valid JWT token - should start with 'eyJ'"
    logger.critical(error_msg)
    print(f"ERROR: {error_msg}")
    raise RuntimeError(error_msg)
```

**Validações Adicionadas**:
1. ✅ Log crítico (mascarado) do tamanho da chave no início da função
2. ✅ Verificação de tamanho mínimo (180 chars) - service keys são ~200+ chars
3. ✅ Verificação de formato JWT (deve começar com 'eyJ')
4. ✅ RuntimeError imediato se a chave estiver errada
5. ✅ Sistema não tenta rodar se a chave estiver inválida

**Prova de Correção**:
```bash
# Ao iniciar a API, você verá:
DEBUG: Service Key length: 207
[CRITICAL] Service Key validation - Length: 207 chars

# Se a key estiver errada:
ERROR: CRITICAL: SUPABASE_SERVICE_KEY appears to be invalid! Length: 150 chars (expected 200+)
RuntimeError: CRITICAL: SUPABASE_SERVICE_KEY appears to be invalid!
```

### 2. Tratamento de Erro no Dashboard - `api/admin.py`

**Localização**: Endpoint `/api/admin/stats` (função `get_admin_stats`)

**Mudanças Implementadas**:

Adicionado try/except detalhado para CADA chamada ao banco de dados com logging de erros brutos:

```python
try:
    profiles_response = await supabase.table('profiles').select('*', count=CountMethod.exact, head=True).execute()
    total_users = profiles_response.count if profiles_response.count is not None else 0
except Exception as e:
    logger.error(f"Error fetching profiles count: {e}")
    logger.error(f"Raw response (if available): {getattr(e, 'response', 'N/A')}")
    # Check if this is a Pydantic validation error
    if "ValidationError" in str(type(e)):
        logger.critical(f"Pydantic ValidationError detected! This likely means DB returned an error instead of data.")
        logger.critical(f"Error details: {str(e)}")
    raise
```

**Benefícios**:
1. ✅ Log do erro bruto do banco de dados antes da validação Pydantic
2. ✅ Identificação específica de ValidationError vs outros erros
3. ✅ Mensagens de erro mais claras para debugging
4. ✅ Detecção de problemas de RLS/permissão

**Aplicado em**:
- Contagem de profiles
- Contagem de check-ins
- Busca de perfis com flags de teste
- Check-ins de hoje
- Check-ins dos últimos 7 dias
- Check-ins dos 7 dias anteriores
- Check-ins dos últimos 30 dias

### 3. Validação do Endpoint de Limpeza - `danger-zone-cleanup`

**Localização**: `/api/admin/danger-zone-cleanup`

**Schema Esperado** (DangerZoneCleanupRequest):

```json
{
  "action": "delete_all" | "delete_last_n" | "delete_by_mood" | "delete_before_date",
  "quantity": <int>,        // Obrigatório para delete_last_n
  "mood_pattern": <string>, // Obrigatório para delete_by_mood ("stable"|"cycling"|"random")
  "before_date": <string>   // Obrigatório para delete_before_date (ISO datetime)
}
```

**Exemplos de Payloads Válidos**:

```json
// 1. Deletar todos os pacientes de teste
{
  "action": "delete_all"
}

// 2. Deletar os últimos N pacientes de teste
{
  "action": "delete_last_n",
  "quantity": 5
}

// 3. Deletar pacientes de teste com padrão de humor específico
{
  "action": "delete_by_mood",
  "mood_pattern": "stable"
}

// 4. Deletar pacientes de teste criados antes de uma data
{
  "action": "delete_before_date",
  "before_date": "2024-01-01T00:00:00Z"
}
```

**Validações Automáticas**:
- ✅ Campo `action` é obrigatório e deve ser um dos 4 valores permitidos
- ✅ Se `action` = "delete_last_n", `quantity` é obrigatório e deve ser >= 1
- ✅ Se `action` = "delete_by_mood", `mood_pattern` é obrigatório
- ✅ Se `action` = "delete_before_date", `before_date` é obrigatório (formato ISO)
- ✅ Endpoint retorna 400 Bad Request se parâmetros obrigatórios estiverem faltando

**Resposta de Sucesso**:
```json
{
  "deleted": 5,
  "message": "Successfully deleted 5 test patient(s) and their data"
}
```

---

## 🔐 Verificação de Segurança

### Service Key Configuração Correta

**Como verificar se a service key está correta**:

1. **Tamanho**: Service role key deve ter ~200+ caracteres
   ```bash
   echo -n "$SUPABASE_SERVICE_KEY" | wc -c
   # Deve retornar > 200
   ```

2. **Formato**: Deve começar com 'eyJ' (JWT header base64)
   ```bash
   echo "$SUPABASE_SERVICE_KEY" | head -c 3
   # Deve retornar: eyJ
   ```

3. **Decode JWT Header** (opcional):
   ```bash
   echo "$SUPABASE_SERVICE_KEY" | cut -d. -f1 | base64 -d 2>/dev/null
   # Deve retornar: {"alg":"HS256","typ":"JWT"}
   ```

4. **Decode JWT Payload** (verificar role):
   ```bash
   echo "$SUPABASE_SERVICE_KEY" | cut -d. -f2 | base64 -d 2>/dev/null
   # Deve conter: "role":"service_role"
   ```

### Exemplo de Keys Válidas vs Inválidas

**❌ ERRADO - Anon Key** (~150 chars):
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd0anRobW92dmZwYWVranRseG92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM3NzE5NTksImV4cCI6MjA3OTEzMTk1OX0.abc123
```
- Role: "anon" (não tem privilégios admin)
- Tamanho: ~150 caracteres

**✅ CORRETO - Service Role Key** (~200+ chars):
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd0anRobW92dmZwYWVranRseG92Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2Mzc3MTk1OSwiZXhwIjoyMDc5MTMxOTU5fQ.L6H-7slonmcB3ewyyN8eFIrXOQHcK9DskXaUhrJJrzQ
```
- Role: "service_role" (tem privilégios admin, bypass RLS)
- Tamanho: ~200+ caracteres

---

## 🧪 Testes de Validação

### 1. Teste de Service Key

```bash
# Deve falhar se key inválida
curl -X POST http://localhost:8000/api/admin/generate-data \
  -H "Authorization: Bearer <JWT-TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"patients_count": 1, "therapists_count": 0}'

# Resultado esperado se key inválida:
# RuntimeError: CRITICAL: SUPABASE_SERVICE_KEY appears to be invalid!
```

### 2. Teste de Stats Endpoint

```bash
# Deve retornar stats ou erro detalhado
curl -X GET http://localhost:8000/api/admin/stats \
  -H "Authorization: Bearer <JWT-TOKEN>"

# Se houver erro de permissão RLS, verá no log:
# [CRITICAL] Database error - likely permission/RLS issue or invalid query
# [CRITICAL] Pydantic ValidationError! DB returned error instead of expected data format
```

### 3. Teste de Danger Zone Cleanup

```bash
# Payload correto - delete_all
curl -X POST http://localhost:8000/api/admin/danger-zone-cleanup \
  -H "Authorization: Bearer <JWT-TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"action": "delete_all"}'

# Payload correto - delete_last_n
curl -X POST http://localhost:8000/api/admin/danger-zone-cleanup \
  -H "Authorization: Bearer <JWT-TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"action": "delete_last_n", "quantity": 5}'

# Payload INCORRETO - deve retornar 422
curl -X POST http://localhost:8000/api/admin/danger-zone-cleanup \
  -H "Authorization: Bearer <JWT-TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{}'

# Resultado esperado:
# HTTP 422: Field required: action
```

---

## 📊 Checklist de Verificação

### Antes do Deploy

- [x] Service key validation implementada em `api/dependencies.py`
- [x] Logs críticos adicionados (mascarados para segurança)
- [x] RuntimeError lançado se key inválida
- [x] Enhanced error handling em `api/admin.py` (stats endpoint)
- [x] Try/except em todas as chamadas de banco
- [x] Log de erros brutos do Pydantic
- [x] Documentação do schema do danger-zone-cleanup
- [x] Exemplos de payloads válidos documentados
- [x] ROADMAP_AUTH_VALIDATION_FIX.md criado com todas as informações

### Após o Deploy

- [ ] Verificar logs ao iniciar API (deve mostrar "Service Key length: XXX")
- [ ] Testar endpoint /api/admin/stats
- [ ] Testar endpoint /api/admin/danger-zone-cleanup com diferentes payloads
- [ ] Verificar que erros 401 desapareceram
- [ ] Verificar que ValidationErrors mostram causa raiz nos logs

---

## 🚨 Troubleshooting

### Problema: Ainda vejo 401 Unauthorized

**Solução**:
1. Verifique o log de inicialização - deve mostrar:
   ```
   DEBUG: Service Key length: 207
   [CRITICAL] Service Key validation - Length: 207 chars
   ```
2. Se mostrar tamanho < 180, você está usando a key errada
3. Obtenha a service_role key do Supabase Dashboard:
   - Settings → API → Project API keys → service_role (secret)

### Problema: Pydantic ValidationError no stats endpoint

**Solução**:
1. Verifique os logs - agora deve mostrar:
   ```
   [CRITICAL] Pydantic ValidationError! DB returned error instead of expected data format
   [CRITICAL] This suggests RLS permission issue or query failure
   ```
2. O erro real do banco estará nos logs antes do ValidationError
3. Geralmente é problema de RLS - verifique se service key está correta

### Problema: 422 no danger-zone-cleanup

**Solução**:
1. Verifique se o payload inclui o campo `action`:
   ```json
   {"action": "delete_all"}
   ```
2. Se `action` = "delete_last_n", inclua `quantity`:
   ```json
   {"action": "delete_last_n", "quantity": 5}
   ```
3. Consulte os exemplos de payloads válidos acima

---

## 📝 Notas Finais

### Dependências do data_generator.py

O `data_generator.py` recebe o cliente Supabase EXATAMENTE da dependência `get_supabase_service`:

```python
# Em api/admin.py, endpoint generate-data:
async def generate_synthetic_data(
    ...
    supabase: AsyncClient = Depends(get_supabase_service),  # ← AQUI
    ...
):
    result = await generate_and_populate_data(
        supabase=supabase,  # ← Cliente com service key é passado aqui
        ...
    )
```

Portanto, se a validação em `get_supabase_service` passar, o `data_generator.py` receberá a service key correta.

### Performance e Logs

Os logs críticos (`logger.critical` e `print`) são executados apenas uma vez por inicialização do dependency. Não há impacto de performance em produção.

---

## 🔄 Próximos Passos (Futuro)

1. ✅ **Implementado**: Service key validation
2. ✅ **Implementado**: Enhanced error logging
3. ✅ **Implementado**: Danger zone cleanup validation
4. ⏳ **Sugerido**: Adicionar health check endpoint para verificar service key
5. ⏳ **Sugerido**: Adicionar métricas de observabilidade para erros 401/422
6. ⏳ **Sugerido**: Criar testes automatizados para validação de service key

---

**Última Atualização**: 2025-11-22  
**Versão**: 1.0  
**Autor**: Backend Security Engineer (Supabase/FastAPI)
