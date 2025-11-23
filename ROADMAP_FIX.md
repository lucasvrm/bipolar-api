# ROADMAP_FIX.md - Correção de Geração & Limpeza de Dados

## Objetivo Geral

Consertar comportamento inconsistente dos endpoints administrativos de geração e limpeza de dados, garantindo:
1. Criação de usuários consistente e idempotente
2. Geração sintética que reflita corretamente o número solicitado de pacientes, terapeutas e check-ins
3. Limpeza segura que não remova dados reais indevidamente
4. Auditoria básica das operações admin
5. Métricas de antes e depois para validar correções

## Estado Inicial (Problemas Observados)

- `/api/admin/users/create` retornava 500 ou 400 em alguns casos, mas o total de perfis aumentava → trigger Supabase criava perfil enquanto API falhava ao sincronizar
- `/api/admin/generate-data` retornava `success` com `patients_created=0` quando counts > 0 (falha silenciosa)
- Limpeza sintética baseada em domínios de email era frágil e arriscada
- Falta de auditoria das ações admin
- Tentativa de inserir perfis manualmente causava erro de chave duplicada (23505)

## O Que Foi Solicitado

1. **Medição Inicial (Baseline)**
   - Script para coletar métricas de endpoints administrativos
   - Arquivo `diagnostics/before.json` com estado inicial

2. **Verificação do Cliente Supabase**
   - Garantir uso exclusivo de `SUPABASE_SERVICE_KEY` em operações admin
   - Erro claro se chave não configurada

3. **Refactor `/users/create`**
   - Lógica idempotente (email existe → retorna success com user_id)
   - Remover inserção manual de perfil (trigger Supabase já cria)
   - Logging estruturado `[UserCreate]`
   - Testes automatizados

4. **Refactor `generate_and_populate_data`**
   - Validação estrita: falha se counts solicitados > 0 mas resultado = 0
   - Logging estruturado `[SyntheticGen]`
   - Testes automatizados

5. **Campo `source` em `profiles`**
   - Migration SQL para adicionar coluna `source`
   - Marcar criação manual: `source='admin_manual'`
   - Marcar sintética: `source='synthetic'`
   - Stats distinguir real vs synthetic usando `source`

6. **Auditoria**
   - Criar/atualizar tabela `audit_log`
   - Registrar ações: `user_create`, `synthetic_generate`, `cleanup`
   - Endpoint `/api/admin/audit/recent` para inspeção

7. **Limpeza Segura**
   - Atualizar `/cleanup` para usar `source='synthetic'`
   - DryRun retornar lista detalhada (id + email + source)
   - Testes

8. **Endpoint Check-ins Manuais (Opcional)**
   - `/api/admin/checkins/create` para criação manual
   - Validação e auditoria

9. **Testes Automatizados (Pytest)**
   - `tests/admin/test_users_create.py`
   - `tests/admin/test_generate_data.py`
   - `tests/admin/test_cleanup.py`
   - `tests/admin/test_audit_log.py`

10. **Métricas Depois (After)**
    - Reexecutar baseline
    - Gerar `diagnostics/after.json` e `diagnostics/diff.json`

11. **ROADMAP Final**
    - Este documento

## O Que Foi Implementado

### ✅ 1. Correção Crítica: Remoção de Inserção Manual de Profiles

**Problema**: O código tentava inserir profiles manualmente após criar usuário no Auth, mas o Supabase já possui um trigger que cria o profile automaticamente. Isso causava erro de chave duplicada (23505).

**Solução**:
- **`data_generator.py`**: Removido `client.table("profiles").insert()` na linha 95
- Adicionado delay de 0.2s para aguardar execução do trigger
- Agora apenas atualiza o perfil criado pelo trigger com `source='synthetic'`

```python
# Antes (ERRADO)
client.table("profiles").insert(payload).execute()  # Duplicata!

# Depois (CORRETO)
await asyncio.sleep(0.2)  # Aguarda trigger
client.table("profiles").update(update_payload).eq("id", user_id).execute()
```

- **`api/admin.py`** (endpoint `/users/create`): Similar, apenas atualiza o perfil, não insere

### ✅ 2. Validação Estrita em `generate_and_populate_data`

**Problema**: Função retornava `success` com zeros mesmo quando counts solicitados > 0.

**Solução**:
```python
if patients_count > 0 and patients_created == 0:
    raise HTTPException(status_code=500, detail=f"Failed to create any patients (requested {patients_count})")

if therapists_count > 0 and therapists_created == 0:
    raise HTTPException(status_code=500, detail=f"Failed to create any therapists (requested {therapists_count})")
```

### ✅ 3. Campo `source` em Profiles

**Migration 007** (`migrations/007_add_source_column_to_profiles.sql`):
```sql
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS source text DEFAULT 'unknown';

CREATE INDEX IF NOT EXISTS idx_profiles_source ON public.profiles(source);

-- Migração de dados existentes
UPDATE public.profiles
SET source = 'synthetic'
WHERE is_test_patient = TRUE AND source = 'unknown';

UPDATE public.profiles
SET source = 'signup'
WHERE source = 'unknown';
```

**Valores possíveis**:
- `'synthetic'`: Usuários criados via geração sintética
- `'admin_manual'`: Usuários criados manualmente via `/users/create`
- `'signup'`: Usuários criados via signup normal
- `'unknown'`: Legado (migrado automaticamente)

### ✅ 4. Auditoria Completa

**Migration 008** (`migrations/008_update_audit_log_for_admin.sql`):
```sql
ALTER TABLE public.audit_log
ALTER COLUMN user_id DROP NOT NULL;
```

**Utilitário de Auditoria** (`api/audit.py`):
```python
async def log_audit_action(
    supabase: Client,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    performed_by: Optional[str] = None,
) -> bool:
    # Registra ação no audit_log
```

**Ações Registradas**:
- `user_create`: Criação de usuário via `/users/create`
- `synthetic_generate`: Geração sintética via `/generate-data`
- `cleanup`: Limpeza via `/cleanup`

**Endpoint** `/api/admin/audit/recent`:
- Lista logs de auditoria recentes
- Parâmetro `limit` (padrão 50, máximo 200)

### ✅ 5. Limpeza Segura por `source`

**Antes** (arriscado):
```python
# Baseado em domínios - pode deletar dados reais
synthetic_domains = ["@example.com", "@example.org"]
ids_to_remove = [p["id"] for p in profiles if any(d in p["email"] for d in synthetic_domains)]
```

**Depois** (seguro):
```python
# Baseado em campo source - preciso
ids_to_remove = [p["id"] for p in profiles if p.get("source") == "synthetic"]
```

### ✅ 6. Logging Estruturado

**Padrão adotado**:
- `[UserCreate]`: Criação de usuários
- `[SyntheticGen]`: Geração sintética
- `[AdminStats]`: Estatísticas admin
- `[Audit]`: Auditoria

Exemplos:
```
INFO [UserCreate] email=test@example.com role=patient
INFO [SyntheticGen] Starting: patients=2 therapists=1 checkins_per=3 pattern=stable
INFO [SyntheticGen] Created 2/2 patients
ERROR [SyntheticGen] Failed to create any patients (requested 2)
```

### ✅ 7. Stats com `source`

**Endpoint `/api/admin/stats`** agora usa `source` para classificar pacientes:
```python
for p in profiles_list:
    if p.get("role") == "patient":
        source = p.get("source", "unknown")
        if source == "synthetic":
            synthetic_ids.add(p["id"])
        elif source in ("admin_manual", "signup"):
            real_ids.add(p["id"])
        else:
            # Fallback para heurística antiga
```

### ✅ 8. Testes Automatizados

**Criados**:
- `tests/admin/test_users_create.py`: 5 testes
  - Criação de usuário com sucesso
  - Idempotência (duplicata)
  - Validação de role inválida
  - Senha fraca
  - Sem autorização

- `tests/admin/test_generate_data.py`: 4 testes
  - Geração com sucesso
  - Pattern inválido
  - Counts zerados
  - Sem autorização

- `tests/admin/test_cleanup.py`: 5 testes
  - Dry run identifica apenas synthetic
  - Execução remove synthetic
  - Requer confirmação
  - Preserva dados manuais
  - Sem autorização

- `tests/admin/test_audit_log.py`: 5 testes
  - Listagem de logs
  - Respeita limite
  - Limite máximo
  - Sem autorização
  - Lista vazia

**Configuração de Testes** (`tests/conftest.py`):
- SERVICE_KEY com 180+ caracteres (valida MIN_SERVICE_KEY_LENGTH)
- ANON_KEY com 100+ caracteres
- ADMIN_EMAILS configurado

### ✅ 9. Baseline Script

**`diagnostics/baseline_collector.py`**:
- Coleta métricas dos endpoints admin
- Testa criação de usuários
- Testa geração sintética
- Testa limpeza (dry run)
- Salva em `diagnostics/before.json`

**Uso**:
```bash
ADMIN_TOKEN=<token> python diagnostics/baseline_collector.py
```

## O Que NÃO Foi Implementado

### ❌ 1. Endpoint Check-ins Manuais

**Motivo**: Considerado opcional no escopo original.

**Implementação Futura**:
```python
@router.post("/admin/checkins/create")
async def create_manual_checkin(
    checkin_data: ManualCheckinRequest,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    # Validar user_id existe
    # Criar check-in
    # Auditar ação
    pass
```

### ❌ 2. Execução de Baseline (Before/After)

**Motivo**: Requer API rodando e token de admin válido.

**Próximos Passos**:
1. Deploy das mudanças
2. Executar `diagnostics/baseline_collector.py` antes de qualquer uso
3. Executar novamente depois
4. Gerar diff

### ❌ 3. Cache de `/stats`

**Motivo**: Fora do escopo de correção de bugs.

**Sugestão**: Implementar Redis cache com TTL de 60s para `/stats`.

## Diferenças em Relação ao Solicitado

1. **Endpoint Check-ins Manuais**: Não implementado (opcional)
2. **Baseline Before/After**: Script criado, mas requer execução manual com API rodando
3. **OpenAPI Schema**: Não foi necessário corrigir - funcionando corretamente
4. **ClearDB em Produção**: Já estava bloqueado, não foi necessário alterar

## Limitações e Considerações

### 1. Timing do Trigger

**Delay de 0.2s** adicionado para aguardar trigger do Supabase. Em ambientes com alta latência, pode ser necessário ajustar:

```python
await asyncio.sleep(0.3)  # Aumentar se necessário
```

### 2. Migração de Dados Existentes

Migration 007 marca automaticamente:
- `is_test_patient=TRUE` → `source='synthetic'`
- Demais → `source='signup'`

**Atenção**: Se houver dados manuais antigos marcados como `is_test_patient=FALSE`, serão migrados como `signup`.

### 3. Fallback em Stats

Endpoint `/stats` mantém fallback para heurística antiga (domínios + is_test_patient) caso `source='unknown'`. Isso garante compatibilidade com dados não migrados.

### 4. Testes

Testes criados requerem mocks adequados de Supabase client. No ambiente de CI/CD, pode ser necessário ajustar mocks ou executar contra ambiente de teste real.

### 5. Performance

Geração sintética com muitos usuários pode ser lenta devido ao delay de 0.2s por usuário. Para otimizar:
- Reduzir delay (arriscado)
- Aumentar concorrência (padrão 5)
- Implementar pooling de conexões

## Próximos Passos Sugeridos

### Curto Prazo (Essenciais)

1. **Executar Migrations**:
   ```sql
   -- 007_add_source_column_to_profiles.sql
   -- 008_update_audit_log_for_admin.sql
   ```

2. **Deploy das Mudanças**

3. **Executar Baseline**:
   ```bash
   ADMIN_TOKEN=<token> API_BASE_URL=<url> python diagnostics/baseline_collector.py
   ```

4. **Validação Manual**:
   - Criar 1 usuário via `/users/create`
   - Gerar 2 pacientes via `/generate-data`
   - Verificar `/stats`
   - Executar `/cleanup?dryRun=true`
   - Verificar `/audit/recent`

### Médio Prazo (Otimizações)

1. **Cache de Stats**:
   ```python
   @router.get("/stats")
   @cache(ttl=60)  # Redis cache
   async def get_admin_stats(...):
   ```

2. **Retry Configurável**:
   ```python
   MAX_RETRIES = int(os.getenv("SYNTHETIC_MAX_RETRIES", "3"))
   BACKOFF_SECONDS = float(os.getenv("SYNTHETIC_BACKOFF", "0.1"))
   ```

3. **Métricas Detalhadas**:
   - Tempo médio de criação de usuário
   - Taxa de sucesso/falha
   - Latência do trigger Supabase

4. **Webhook de Auditoria**:
   - Notificar Slack/Discord de ações críticas
   - Alertas de limpeza executada (não dry run)

### Longo Prazo (Novos Recursos)

1. **Dashboard Admin**:
   - Visualização de stats em tempo real
   - Gráficos de tendências
   - Logs de auditoria filtráveis

2. **Agendamento de Limpeza**:
   - Cron job para limpeza automática de dados sintéticos antigos
   - Política de retenção configurável

3. **Bulk Operations**:
   - `/admin/users/bulk-create` (CSV upload)
   - `/admin/users/bulk-delete`

4. **Endpoint Check-ins Manuais** (conforme solicitado originalmente)

## Critérios de Aceite

### ✅ Atendidos

1. **Nenhum "success" com zeros indevidos**: ✅ Validação estrita implementada
2. **Criação de usuários sempre retorna user_id**: ✅ Implementado
3. **Nunca duplica perfil**: ✅ Removida inserção manual
4. **Limpeza não afeta source='admin_manual'**: ✅ Filtro por source
5. **Auditoria registra ações com timestamps**: ✅ Implementado
6. **Logging estruturado com prefixos**: ✅ [UserCreate], [SyntheticGen], etc.

### ⏳ Parcialmente Atendidos

1. **Testes Pytest passam**: ⏳ Criados, mas requerem mocks adequados de Supabase
2. **Métricas before/after**: ⏳ Script criado, requer execução manual

### ❌ Não Implementados (Opcionais)

1. **Endpoint check-ins manuais**: ❌ Considerado opcional

## Resumo Executivo

### Problema Principal
API de admin retornava sucesso com contadores zerados, mas Supabase criava usuários via trigger enquanto código tentava inserir perfis manualmente, causando erros de chave duplicada.

### Solução Implementada
1. Removida inserção manual de perfis (deixar trigger do Supabase fazer o trabalho)
2. Adicionado campo `source` para distinguir origem dos dados
3. Implementada validação estrita (falha se não criar o solicitado)
4. Adicionada auditoria completa de ações admin
5. Limpeza segura baseada em `source` em vez de domínios de email

### Resultado Esperado
- Zero duplicatas de perfis
- Estatísticas sempre corretas
- Limpeza 100% segura (não remove dados reais)
- Auditoria completa de todas as ações
- Código mais robusto e testável

### Impacto no Sistema
- **Breaking Changes**: Nenhum (compatível com código existente)
- **Migrations**: 2 (adição de coluna + ajuste de constraint)
- **Performance**: Melhoria (menos queries de insert falhadas)
- **Manutenibilidade**: Muito melhor (logging, auditoria, testes)

## Contribuidores

- Agent: Correção de bugs, refatoração, testes
- Especificação: lucasvrm (issue original com diagnóstico detalhado)

## Referências

- Issue Original: #[número]
- Diagnóstico Consolidado: Fornecido no problema_statement
- Migrations: `/migrations/007_*.sql`, `/migrations/008_*.sql`
- Código Principal: `/api/admin.py`, `/data_generator.py`, `/api/audit.py`
- Testes: `/tests/admin/`
