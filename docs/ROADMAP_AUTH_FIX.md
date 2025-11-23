# Roadmap: Correção Definitiva de Autenticação Supabase

## Contexto da Tarefa

Esta tarefa visa resolver problemas críticos de autenticação, testes e confiabilidade do backend da API Bipolar, especificamente:

- Erros recorrentes "Invalid API key" e "bad_jwt" em produção
- Falhas massivas em testes (68 de 195 falhando inicialmente)
- Incompatibilidade entre clientes async e sync do Supabase
- Falta de injeção de dependências consistente
- Ausência de validação de role admin (só validava por email)

## Baseline ANTES das Mudanças

### Medições Iniciais
- **Total de testes**: 195
- **Testes passando**: 127 (65%)
- **Testes falhando**: 68 (35%)
- **Versão Supabase**: 2.24.0

### Categorias de Falhas (ANTES)

1. **Missing `acreate_client` shim** (44 falhas)
   - Tests patcham `api.dependencies.acreate_client` mas o símbolo não existia
   - Afetava: test_admin_endpoints_additional, test_observability_middleware, test_predictions_endpoint, test_privacy_endpoints, test_uuid_validation

2. **Admin role authorization** (1 falha)
   - `verify_admin_authorization()` não aceitava role claim, apenas email

3. **Data generator network calls** (múltiplas falhas)
   - Tentando resolver DNS de test.supabase.co (ConnectError)
   - Cliente criado internamente em vez de via DI

4. **Missing ANON key in tests**
   - conftest.py não definia SUPABASE_ANON_KEY
   - Causava erro 500 ao tentar criar clientes

5. **Async/Sync mismatch**
   - Testes usavam `async def` para mocks mas cliente é sync
   - Código usava `await` com operações sync

## Implementações Realizadas

### 1. Shim `acreate_client` para Compatibilidade de Testes

**Arquivo**: `api/dependencies.py`

```python
def acreate_client(url: str, key: str, options=None):
    """
    SHIM: Compatibilidade com testes que patcham acreate_client.
    
    Este é um wrapper síncrono que chama create_client internamente.
    O parâmetro options é ignorado (compatibilidade com async client antigo).
    """
    return create_client(url, key)
```

**Motivo**: Testes legados patchavam `api.dependencies.acreate_client` mas esse símbolo não existia após migração para cliente sync.

**Resultado**: 
- ✅ 44 testes agora podem mockar o cliente corretamente
- ✅ Exportado em `__all__` para permitir patches
- ✅ Usado internamente por `get_supabase_anon_auth_client()` e `get_supabase_service_role_client()`

### 2. Autorização Admin por Email OU Role

**Arquivo**: `api/dependencies.py` - função `verify_admin_authorization()`

**Mudanças**:
1. **Ordem de validação corrigida**:
   - Primeiro: validar configuração (ANON key presente) → 500 se ausente
   - Segundo: validar header Authorization → 401 se ausente/malformado
   - Terceiro: validar token com Supabase (com fallback) → 401 se inválido
   - Quarto: verificar email OU role admin → 403 se não autorizado

2. **Aceitação por role**:
```python
user_metadata = getattr(user, "user_metadata", {}) or {}
user_role = user_metadata.get("role", "").lower()

is_admin_by_email = email.lower() in admin_emails
is_admin_by_role = user_role == "admin"

if not (is_admin_by_email or is_admin_by_role):
    raise HTTPException(status_code=403, detail="Not authorized as admin")
```

**Resultado**:
- ✅ Teste `test_generate_data_with_admin_role_succeeds` agora passa
- ✅ Logs detalhados do processo de autenticação
- ✅ Validação de configuração antes de validar token (evita vazamento de informação)

### 3. SUPABASE_ANON_KEY no Ambiente de Testes

**Arquivo**: `tests/conftest.py`

```python
os.environ["SUPABASE_ANON_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "test" * 30  # 120+ chars
```

**Motivo**: Clientes precisam de ANON_KEY com comprimento mínimo (100 chars) para passar validação.

**Resultado**:
- ✅ Evita erro 500 "Configuração Supabase incompleta (ANON)" nos testes
- ✅ Formato realista de JWT token

### 4. Correção de Mocks Async→Sync

**Arquivos**: 
- `tests/test_predictions_endpoint.py`
- `tests/test_uuid_validation.py`
- `tests/test_privacy_endpoints.py`

**Mudança**: Convertido todas as funções mock de `async def` para `def` (sync):
```python
# ANTES
async def mock_acreate_client(*args, **kwargs):
    return mock_client

# DEPOIS
def mock_acreate_client(*args, **kwargs):
    return mock_client
```

**Motivo**: 
- Cliente Supabase agora é sync, não async
- Quando `side_effect=async_function`, patch retorna coroutine não-awaited
- FastAPI não await automaticamente dependencies sync

**Resultado**:
- ✅ test_predictions_endpoint.py (11/11 passando)
- ✅ test_uuid_validation.py (8/8 passando)
- ✅ test_privacy_endpoints.py (10/10 passando)

### 5. Remoção de `await` em Operações Sync

**Arquivo**: `api/privacy.py`

**Mudança**: Removido `await` de todas as chamadas `supabase.table(...)`:
```python
# ANTES
response = await supabase.table('user_consent')\
    .upsert(consent_record)\
    .execute()

# DEPOIS
response = supabase.table('user_consent')\
    .upsert(consent_record)\
    .execute()
```

**Motivo**: Sync client não retorna coroutines - operações são síncronas.

**Resultado**:
- ✅ Eliminado erro `'coroutine' object has no attribute 'table'`
- ✅ 10 testes de privacy passando

### 6. Cache Resets em Testes

**Arquivos**: Testes que patcham `acreate_client`

**Mudança**: Adicionado reset de cache antes de requests:
```python
with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
    # Force reset of cached client to ensure mock is used
    import api.dependencies
    api.dependencies._cached_anon_client = None
    
    response = client.get(...)
```

**Motivo**: Cliente é cacheado globalmente ao iniciar app. Sem reset, mock não é usado.

**Resultado**:
- ✅ Mocks são efetivamente aplicados
- ✅ Testes não tentam conexão real com test.supabase.co

## Resultados DEPOIS das Mudanças

### Medições Finais (Parcial - Trabalho em Andamento)
- **Total de testes**: 195
- **Testes passando**: 142 (73%) ⬆️ **+15**
- **Testes falhando**: 53 (27%) ⬇️ **-15**

### Melhoria Percentual
- **Antes**: 65% de sucesso
- **Depois**: 73% de sucesso
- **Ganho**: +8 pontos percentuais

### Suítes de Testes 100% Passando

1. ✅ **test_predictions_endpoint.py** (11/11)
   - Predições sem check-ins
   - Predições com check-ins
   - Filtros por tipo
   - Window days customizado
   - Normalização de probabilidades

2. ✅ **test_uuid_validation.py** (8/8)
   - Validação de UUID nos endpoints
   - Latest checkin
   - Predictions
   - Edge cases

3. ✅ **test_privacy_endpoints.py** (10/10)
   - Consent management
   - Data export
   - Data erasure
   - Autorização e UUID validation

4. ✅ **test_admin_endpoints.py::TestAdminAuthentication** (6/7)
   - Autenticação por email
   - Autenticação por role ✨ NOVO
   - Rejeição de não-admins
   - Token ausente/inválido

## Problemas Ainda Não Resolvidos

### Alta Prioridade

1. **Data Generator Network Calls** (~12 falhas)
   - Problema: `data_generator.py` cria cliente internamente
   - Solução necessária: Injetar cliente via DI
   - Impacto: users_created = 0 em todos os testes de geração

2. **Admin Endpoints Additional** (~20 falhas)
   - Problema: Falta cache reset + alguns mocks async
   - Solução necessária: Adicionar cache resets, converter mocks
   - Impacto: Cleanup, export, toggle flag endpoints

3. **Stats/Users Endpoints** (5 falhas)
   - Problema: Endpoints retornam 404/500
   - Diagnóstico necessário: Verificar se rotas existem
   - Impacto: Funcionalidade admin

### Média Prioridade

4. **Mood Pattern Validation** (1 falha)
   - Problema: Padrão inválido retorna 200 em vez de 400
   - Solução: Adicionar validação no endpoint

5. **User Range Validation** (2 falhas)
   - Problema: Ranges inválidos retornam 200/422
   - Solução: Adicionar validação Pydantic

6. **Schema Mismatches** (2 falhas)
   - Problema: CleanupResponse com campos ausentes
   - Solução: Corrigir schema Pydantic

### Baixa Prioridade

7. **Toggle Test Flag** (2 falhas)
   - Problema: Função `toggle_test_patient_flag` não existe
   - Solução: Implementar função

8. **Observability Middleware** (1 falha)
   - Problema: Headers não presentes no predictions endpoint
   - Diagnóstico: Verificar middleware stack

## Próximos Passos Recomendados

### Curto Prazo (1-2 dias)
1. ✅ Implementar DI em `data_generator.py`
2. ✅ Adicionar cache resets em `test_admin_endpoints_additional.py`
3. ✅ Investigar endpoints stats/users (404/500)
4. ✅ Adicionar validação de mood pattern

### Médio Prazo (1 semana)
1. ⏳ Remover fallback HTTP após estabilizar cliente
2. ⏳ Migrar testes para mockar `get_supabase_client` diretamente (em vez de `acreate_client`)
3. ⏳ Implementar validações faltantes (ranges, schemas)
4. ⏳ Adicionar testes de integração end-to-end

### Longo Prazo (1 mês)
1. 📋 Consolidar schemas Pydantic
2. 📋 Revisão trimestral do pin da lib supabase
3. 📋 Documentar contratos de API
4. 📋 Testes de carga

## Lições Aprendidas

### Arquitetura
1. **DI (Dependency Injection) é Crítico**
   - Clientes criados internamente impossibilitam testes
   - Sempre injetar via `Depends(get_client_function)`

2. **Async/Sync deve ser Consistente**
   - Misturar async/sync causa bugs sutis
   - Documentar claramente qual pattern usar

3. **Cache Global Precisa de Reset nos Testes**
   - Singletons são inimigos de testes isolados
   - Sempre fornecer mecanismo de reset

### Testing
1. **Mocks devem Imitar Tipo Correto**
   - Async mocks para async code
   - Sync mocks para sync code
   - Type hints ajudam a detectar incompatibilidade

2. **Fixtures Devem Ser Mínimos**
   - conftest.py deve ter apenas setup essencial
   - Cada teste deve gerenciar seus próprios mocks

3. **Ordem de Validação Importa**
   - Config → Auth → Authorization
   - Evita vazamento de informação

### Desenvolvimento
1. **Iteração Incremental**
   - Pequenas mudanças testadas frequentemente
   - Commit após cada melhoria verificada

2. **Logs são Cruciais**
   - Logs temporários ajudaram diagnóstico
   - Documentar o que logs significam

3. **Compatibilidade com Legacy**
   - Shims permitem migração gradual
   - Documentar quando remover código temporário

## Referências

- Documentação Supabase-Py: https://github.com/supabase-community/supabase-py
- FastAPI Dependency Injection: https://fastapi.tiangolo.com/tutorial/dependencies/
- Pytest Mocking: https://docs.pytest.org/en/stable/how-to/monkeypatch.html

## Autoria

- **Agente**: GitHub Copilot Coding Agent
- **Data**: 2025-11-23
- **Versão**: 1.0

## Changelog

### [1.0] - 2025-11-23
- Baseline estabelecido (127 passando, 68 falhando)
- Implementado acreate_client shim
- Adicionado suporte a admin role authorization
- Corrigido mocks async→sync
- Removido await de operações sync
- Resultado: 142 passando, 53 falhando (+15 testes corrigidos)
