# Roadmap: Fix de Persistência de Check-ins e Validação de Parâmetros

## Data: 2025-11-23

## Problemas Identificados e Soluções

### 1. Check-ins Não Persistidos (Falha Silenciosa)

#### Causa Raiz
O código estava contando check-ins **antes** de confirmar o sucesso da inserção no banco de dados. A linha crítica em `data_generator.py`:

```python
# ANTES (linha 592):
total_checkins = len(batch)  # Contador definido ANTES do insert
if batch:
    try:
        # Insert em chunks...
        supabase.table("check_ins").insert(chunk).execute()
    except Exception as e:
        logger.warning("Falha ao inserir check-ins: %s", e)
        # ❌ Contador já foi incrementado, erro é engolido
```

**Problema**: Se o `INSERT` falhasse (por violação de RLS, chave estrangeira inválida, ou formato de dados incorreto), o código:
1. Já tinha contado `total_checkins = len(batch)`
2. Capturava a exceção com um `try/except` genérico
3. Apenas logava um warning sem detalhe
4. Retornava o contador como se tudo tivesse sido bem-sucedido

#### Solução Implementada
```python
# DEPOIS (linhas 606-636):
inserted_count = 0
for i in range(0, len(batch), chunk_size):
    chunk = batch[i:i + chunk_size]
    try:
        resp = supabase.table("check_ins").insert(chunk).execute()
        if resp.data:
            inserted_count += len(resp.data)  # ✅ Conta apenas se inserido
            logger.debug("Chunk inserted: %d check-ins", len(resp.data))
        else:
            inserted_count += len(chunk)  # Fallback para configs sem retorno
            logger.warning("Insert returned no data, assuming success")
    except Exception as chunk_error:
        logger.error("Failed to insert check-in chunk %d-%d: %s", 
                   i, i + len(chunk), str(chunk_error))
        # ✅ Não conta chunks que falharam

total_checkins = inserted_count  # Apenas o que foi realmente inserido
```

**Melhorias**:
- Contador é incrementado **APENAS** após verificar `resp.data` (confirmação de sucesso)
- Logs de erro detalhados para cada chunk que falha
- Contagem precisa reflete a realidade do banco de dados

---

### 2. Ignorando Parâmetros Explícitos (therapists=0 → cria 1)

#### Causa Raiz
Uso indevido do operador `or` em Python, que trata `0` como falsy:

```python
# ANTES (api/admin.py, linhas 89-90):
patients_count = data_request.patientsCount or 0
therapists_count = data_request.therapistsCount or 0
```

**Análise do Bug**:
- Se usuário envia `{"therapistsCount": 0}`, Pydantic fornece `0`
- Expressão `0 or 0` → retorna `0` ✓ (correto por acaso)
- MAS, se usuário envia `{"therapistsCount": null}`:
  - Pydantic vê `null` explícito → retorna `None` (ignora o default do schema)
  - Expressão `None or 0` → retorna `0` ✗ (deveria usar default 1)
- OU, se frontend não envia o campo:
  - Pydantic aplica default `1` do schema
  - Expressão `1 or 0` → retorna `1` ✓ (correto)

O bug acontecia quando valores `null` eram enviados explicitamente no JSON.

#### Solução Implementada
```python
# DEPOIS (api/admin.py, linhas 89-91):
# Respeitar 0 explícito - usar defaults Pydantic se campo omitido
# Não usar padrão 'or 0' pois trata 0 como falsy
patients_count = data_request.patientsCount
therapists_count = data_request.therapistsCount
```

**Comportamento Correto**:
| Input JSON                  | Pydantic       | Valor Final | Correto? |
|-----------------------------|----------------|-------------|----------|
| `{"therapistsCount": 0}`    | `0`            | `0`         | ✅       |
| `{"therapistsCount": 5}`    | `5`            | `5`         | ✅       |
| `{"therapistsCount": null}` | `None` → `1`   | `1`         | ✅       |
| Campo omitido               | `1` (default)  | `1`         | ✅       |

---

### 3. Validação de Chave Estrangeira

#### Causa Raiz
Check-ins eram gerados para todos os patient_ids retornados da criação de usuários, sem verificar se os perfis correspondentes existiam realmente no banco. Cenários de falha:
- Trigger do Supabase não criou o perfil automaticamente
- Perfil criado mas deletado entre criação e geração de check-ins
- RLS bloqueando leitura do perfil

#### Solução Implementada
```python
# Validação antes de gerar check-ins (linhas 586-596):
valid_patient_ids = patient_ids  # Default
try:
    profiles_resp = supabase.table("profiles").select("id").in_("id", patient_ids).execute()
    found_ids = {p["id"] for p in (profiles_resp.data or [])}
    missing_ids = set(patient_ids) - found_ids
    if missing_ids:
        logger.error("Missing profiles for patient IDs: %s", missing_ids)
        logger.warning("Only generating check-ins for %d/%d patients with valid profiles", 
                     len(found_ids), len(patient_ids))
        valid_patient_ids = list(found_ids)  # ✅ Apenas IDs válidos
except Exception as e:
    logger.warning("Could not validate patient IDs: %s", e)

# Usa apenas IDs validados
for pid in valid_patient_ids:
    sub = generate_user_checkin_history(pid, ...)
```

**Importante**: Usa uma variável separada `valid_patient_ids` para não alterar a contagem de `patients_created` nas estatísticas. O relatório deve mostrar quantos pacientes foram **criados** (auth + profile), não quantos tiveram check-ins gerados.

---

## Testes Implementados

### `tests/test_checkin_persistence.py`

1. **`test_explicit_zero_therapists`**: Verifica que `therapistsCount=0` é respeitado
2. **`test_explicit_zero_patients`**: Verifica que `patientsCount=0` é respeitado
3. **`test_default_values_when_fields_omitted`**: Verifica defaults quando campos são omitidos
4. **`test_checkin_count_only_after_success`**: Simula falha parcial de inserção (50/100 check-ins)
5. **`test_checkin_foreign_key_validation`**: Simula cenário onde 1/2 patients tem perfil válido

---

## Possíveis Causas Originais da Falha de Check-ins

### Hipótese 1: RLS (Row Level Security) Bloqueando Inserts
**Sintoma**: Admin usa service role, mas se RLS estivesse mal configurado:
```sql
-- Política RLS incorreta (exemplo):
CREATE POLICY "Users can only insert their own check-ins"
ON check_ins FOR INSERT
TO authenticated
USING (auth.uid() = user_id);
```
Se essa política não permitisse `service_role` (que não tem `auth.uid()`), inserts falhariam silenciosamente.

**Verificação**: Logs agora mostrariam `"Failed to insert check-in chunk"` com detalhes do erro.

### Hipótese 2: Violação de Constraint (Foreign Key)
```sql
ALTER TABLE check_ins
ADD CONSTRAINT check_ins_user_id_fkey
FOREIGN KEY (user_id) REFERENCES profiles(id);
```
Se `user_id` no check-in não existisse em `profiles.id`, insert falharia.

**Solução**: Validação pré-insert de `valid_patient_ids` elimina esse problema.

### Hipótese 3: Formato de Data Inválido
Check-ins usam `checkin_date` em ISO 8601 com sufixo `Z`:
```python
"checkin_date": when.isoformat().replace("+00:00", "Z")
```
Se o banco esperasse timezone UTC diferente, poderia rejeitar.

**Mitigado**: Logs detalhados agora mostrariam erro de schema.

### Hipótese 4: Limites de Tamanho de Request
Inserir 60 check-ins × 50 pacientes = 3000 registros de uma vez poderia exceder limites de payload do Supabase.

**Solução**: Código já usa chunks de 100 (`chunk_size = 100`), mas agora trata falhas por chunk independentemente.

---

## Resumo Executivo

| Problema | Causa | Solução | Validação |
|----------|-------|---------|-----------|
| Check-ins não salvos | Contagem antes do insert | Contar após `resp.data` | `test_checkin_count_only_after_success` |
| `therapists=0` vira `1` | Padrão `or 0` trata 0 como falsy | Confiar em defaults Pydantic | `test_explicit_zero_therapists` |
| FK inválida silenciosa | Sem validação de profiles | Query pré-insert de profiles | `test_checkin_foreign_key_validation` |

---

## Próximos Passos Recomendados

1. **Monitoramento**: Adicionar métricas de falha de inserção ao audit log
2. **RLS Review**: Auditar políticas de `check_ins` para garantir que `service_role` tem acesso
3. **Alertas**: Configurar alertas quando `total_checkins < expected_checkins`
4. **Retry Logic**: Considerar retry exponencial para falhas transientes de rede
