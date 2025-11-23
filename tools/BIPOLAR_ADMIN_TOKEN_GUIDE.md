# BIPOLAR_ADMIN_TOKEN - Guia Completo

## O que é o BIPOLAR_ADMIN_TOKEN?

O `BIPOLAR_ADMIN_TOKEN` é um **JWT (JSON Web Token)** de autenticação usado para acessar os endpoints administrativos da API Bipolar em produção.

### Características do Token

- **Tipo:** Bearer Token (JWT)
- **Formato:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` (Base64 encoded)
- **Propósito:** Autenticação de usuários com privilégios administrativos
- **Scope:** Acesso aos endpoints `/api/admin/*`
- **Validação:** Verificado pela função `verify_admin_authorization` em `api/dependencies.py`

## Como Obter o Token

### Método 1: Login via API (Recomendado)

1. **Fazer login como usuário admin:**

```bash
# Endpoint de autenticação (ajuste conforme sua implementação)
curl -X POST https://bipolar-api.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "sua-senha-admin"
  }'
```

2. **Extrair o token da resposta:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLWlkIiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzAwMDAwMDAwfQ.signature",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

3. **Usar o access_token:**

```bash
export BIPOLAR_ADMIN_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Método 2: Via Supabase Dashboard

Se você usa Supabase para autenticação:

1. **Acesse o Supabase Dashboard:**
   - Vá para https://app.supabase.com
   - Selecione seu projeto

2. **Navegue até Authentication → Users:**
   - Encontre o usuário admin
   - Verifique que o campo `role` está definido como `"admin"` nos metadados

3. **Gere um token JWT:**
   
   **Opção A - Usando a interface do Supabase:**
   - No painel de usuário, clique em "Generate new JWT"
   - Copie o token gerado

   **Opção B - Programaticamente com Supabase CLI:**
   ```bash
   # Login como o usuário admin
   supabase auth login \
     --email admin@example.com \
     --password sua-senha
   
   # O token será retornado na resposta
   ```

### Método 3: Token de Desenvolvimento/Teste

Para ambientes de desenvolvimento local:

1. **Crie um usuário admin no banco:**

```sql
-- No Supabase SQL Editor
INSERT INTO auth.users (email, encrypted_password, email_confirmed_at, role)
VALUES (
  'admin@example.com',
  crypt('sua-senha', gen_salt('bf')),
  NOW(),
  'authenticated'
);

-- Adicione metadata de admin no perfil
INSERT INTO public.profiles (id, email, role)
VALUES (
  (SELECT id FROM auth.users WHERE email = 'admin@example.com'),
  'admin@example.com',
  'admin'
);
```

2. **Faça login via API para obter o token**

## Validação do Token

### Como Verificar se o Token é Válido

A API valida o token através de dois mecanismos:

1. **Verificação JWT via Supabase:**
   ```python
   # api/dependencies.py
   response = supabase.auth.get_user(token)
   user = response.user
   ```

2. **Verificação de Role Admin:**
   ```python
   # Verifica se o email do usuário está na lista de admins
   admin_emails = os.getenv("ADMIN_EMAILS", "").split(",")
   is_admin = user.email in admin_emails
   ```

### Testar Manualmente

```bash
# Teste se o token funciona
curl -X GET https://bipolar-api.onrender.com/api/admin/stats \
  -H "Authorization: Bearer $BIPOLAR_ADMIN_TOKEN"

# Resposta esperada (200 OK):
{
  "total_users": 123,
  "total_checkins": 456,
  ...
}

# Se o token for inválido (401 Unauthorized):
{
  "detail": "Invalid authentication credentials"
}
```

## Configuração de Usuários Admin

### Variável de Ambiente ADMIN_EMAILS

Para que um usuário seja reconhecido como admin, seu email deve estar na variável de ambiente `ADMIN_EMAILS`:

```bash
# No arquivo .env ou nas variáveis de ambiente do servidor
ADMIN_EMAILS=admin@example.com,outro-admin@example.com
```

### Verificação no Código

Localização: `api/dependencies.py`

```python
def verify_admin_authorization(authorization: str = Header(None)):
    """
    Verifica se o usuário autenticado tem privilégios de admin.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    
    token = authorization.replace("Bearer ", "")
    
    # Valida o token com Supabase
    response = supabase.auth.get_user(token)
    user = response.user
    
    # Verifica se o email está na lista de admins
    admin_emails = get_admin_emails()
    if user.email.lower() not in admin_emails:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    
    return True
```

## Estrutura do Token JWT

Um token JWT típico possui três partes separadas por pontos:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLWlkIiwicm9sZSI6ImFkbWluIn0.signature
│────────── Header ──────────│──────── Payload ────────│─ Signature ─│
```

### Decodificação (apenas para inspeção, NÃO para autenticação)

Você pode decodificar o token em https://jwt.io para inspecionar:

**Header:**
```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

**Payload:**
```json
{
  "sub": "user-id-uuid",
  "email": "admin@example.com",
  "role": "authenticated",
  "aud": "authenticated",
  "exp": 1700000000,
  "iat": 1699996400
}
```

**⚠️ IMPORTANTE:** Nunca confie apenas na decodificação do token. Sempre valide a assinatura usando a SECRET_KEY.

## Segurança

### Boas Práticas

1. **Nunca compartilhe o token:**
   - Tokens admin têm privilégios elevados
   - Trate como uma senha

2. **Rotação de tokens:**
   - Tokens JWT têm expiração (campo `exp`)
   - Renove o token periodicamente fazendo novo login

3. **Armazenamento seguro:**
   ```bash
   # ✅ BOM - Variável de ambiente
   export BIPOLAR_ADMIN_TOKEN="token-aqui"
   
   # ❌ RUIM - Hardcoded no código
   token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
   ```

4. **Use em HTTPS apenas:**
   - Nunca envie tokens por HTTP não-criptografado

5. **Limite de acesso:**
   - Configure `ADMIN_EMAILS` apenas com usuários confiáveis

### Revogação de Tokens

Se um token foi comprometido:

1. **Remova o email da variável ADMIN_EMAILS:**
   ```bash
   # Antes
   ADMIN_EMAILS=admin@example.com,comprometido@example.com
   
   # Depois
   ADMIN_EMAILS=admin@example.com
   ```

2. **Desabilite o usuário no Supabase:**
   - Authentication → Users → [usuário] → Disable

3. **Reinicie a aplicação para limpar caches**

## Troubleshooting

### Token não funciona

**Erro:** `401 Unauthorized`

**Soluções:**
1. Verifique se o token começa com `Bearer ` no header
2. Verifique se o token não expirou (campo `exp`)
3. Faça novo login para obter token atualizado

**Erro:** `403 Forbidden - Admin privileges required`

**Soluções:**
1. Verifique se o email está em `ADMIN_EMAILS`
2. Verifique se a variável de ambiente está carregada no servidor
3. Reinicie o servidor após alterar `ADMIN_EMAILS`

### Como verificar expiração do token

```python
import jwt
import json
from datetime import datetime

token = "seu-token-aqui"

# Decodifica SEM validar (apenas para inspeção)
decoded = jwt.decode(token, options={"verify_signature": False})
exp_timestamp = decoded.get("exp")

if exp_timestamp:
    exp_date = datetime.fromtimestamp(exp_timestamp)
    print(f"Token expira em: {exp_date}")
    
    if datetime.now() > exp_date:
        print("⚠️ Token EXPIRADO - faça novo login")
    else:
        print("✅ Token ainda válido")
```

## Exemplos de Uso com o Script de Teste

### Exemplo Completo

```bash
#!/bin/bash

# 1. Obter o token (exemplo com curl)
RESPONSE=$(curl -s -X POST https://bipolar-api.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "senha-secreta"
  }')

# 2. Extrair o token da resposta JSON
TOKEN=$(echo $RESPONSE | jq -r '.access_token')

# 3. Exportar como variável de ambiente
export BIPOLAR_ADMIN_TOKEN="$TOKEN"

# 4. Executar o script de teste
python tools/test_admin_endpoints_production.py

# 5. Verificar resultado
if [ $? -eq 0 ]; then
    echo "✅ Testes concluídos com sucesso"
else
    echo "❌ Testes failharam - verificar relatórios"
fi
```

### Uso em CI/CD (GitHub Actions)

```yaml
- name: Run admin endpoint tests
  env:
    BIPOLAR_ADMIN_TOKEN: ${{ secrets.ADMIN_JWT_TOKEN }}
  run: python tools/test_admin_endpoints_production.py
```

**Setup do Secret:**
1. GitHub Repository → Settings → Secrets → Actions
2. New repository secret
3. Name: `ADMIN_JWT_TOKEN`
4. Value: (cole o token JWT)
5. Add secret

## Alternativas (Futuras)

### Service Account Tokens (Recomendado para produção)

Em vez de usar tokens de usuário, considere implementar:

```python
# api/dependencies.py (futura implementação)
def verify_service_account():
    """Valida service account token (não JWT de usuário)"""
    token = os.getenv("SERVICE_ACCOUNT_TOKEN")
    # Validação específica para service accounts
```

**Benefícios:**
- Não expira
- Não vinculado a usuário específico
- Pode ter permissões granulares

## Resumo

| Aspecto | Valor |
|---------|-------|
| **Formato** | JWT (Bearer Token) |
| **Onde obter** | Login via API, Supabase Dashboard, ou geração programática |
| **Como usar** | `export BIPOLAR_ADMIN_TOKEN="token-jwt"` |
| **Validação** | Via Supabase Auth + verificação de email em ADMIN_EMAILS |
| **Expiração** | Sim (campo `exp` no JWT) |
| **Segurança** | Tratar como senha, usar HTTPS, nunca commitar |
| **Renovação** | Fazer novo login quando expirar |

## Suporte

Se você ainda tiver dúvidas:

1. ✅ Verifique os logs da aplicação para erros de autenticação
2. ✅ Use https://jwt.io para inspecionar o token (sem validar)
3. ✅ Teste manualmente com `curl` antes de usar no script
4. ✅ Verifique a configuração de `ADMIN_EMAILS` no servidor

---

**Documentação criada em:** 2024-11-23  
**Relacionado a:** `tools/test_admin_endpoints_production.py`  
**Versão da API:** 2.0.0
