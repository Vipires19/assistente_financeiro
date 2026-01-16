# 🔒 Segurança Multi-Usuário - Documentação

## 🎯 Visão Geral

Sistema de controle multi-usuário com isolamento completo de dados entre usuários.

**Princípio Fundamental**: Nenhum usuário pode acessar dados de outro usuário.

---

## 🛡️ Pontos Críticos de Segurança

### 1. **Nunca Confiar em user_id do Cliente**

❌ **ERRADO**:
```python
# NUNCA faça isso!
user_id = request.GET.get('user_id')  # Cliente pode enviar qualquer ID
```

✅ **CORRETO**:
```python
# Sempre do usuário autenticado (middleware)
user_id = str(request.user_mongo['_id'])
# ou
user_id = request.user_id  # Injetado pelo SecurityMiddleware
```

**Por quê?**: Cliente pode modificar parâmetros HTTP. Sempre usar dados da sessão autenticada.

---

### 2. **Sempre Filtrar por user_id no MongoDB**

❌ **ERRADO**:
```python
# Busca sem filtrar por user_id
transactions = repo.find_many({'type': 'expense'})
```

✅ **CORRETO**:
```python
# Sempre filtrar por user_id primeiro
transactions = repo.find_many({
    'user_id': ObjectId(user_id),  # CRÍTICO: Sempre primeiro
    'type': 'expense'
})
```

**Por quê?**: Sem filtro, usuário pode ver dados de todos. Filtro por user_id garante isolamento.

---

### 3. **Validar user_id em Queries por ID**

❌ **ERRADO**:
```python
# Busca por ID sem validar user_id
transaction = repo.find_by_id(transaction_id)
if transaction['user_id'] != user_id:  # Muito tarde!
    raise Error()
```

✅ **CORRETO**:
```python
# Valida user_id na query
transaction = repo.find_by_id(transaction_id, user_id=user_id)
# Se não encontrar, retorna None (não revela se existe)
```

**Por quê?**: Validação na query é mais segura e eficiente. Evita vazamento de informação.

---

### 4. **Middleware de Segurança**

O `SecurityMiddleware` injeta `user_id` no request:

```python
# request.user_id sempre disponível
user_id = request.user_id  # Do usuário autenticado
```

**Por quê?**: Centraliza extração de user_id, evitando erros de implementação.

---

### 5. **Validação em Services**

Todos os services validam `user_id`:

```python
def get_dashboard_data(self, user_id: str, period: str = 'mensal'):
    if not user_id:
        raise ValueError("user_id é obrigatório")
    # ...
```

**Por quê?**: Fail-fast. Erro imediato se user_id não fornecido.

---

### 6. **Agregações MongoDB**

Sempre filtrar por `user_id` primeiro no `$match`:

```python
pipeline = [
    {
        '$match': {
            'user_id': ObjectId(user_id),  # CRÍTICO: Primeiro filtro
            'type': 'expense',
            # outros filtros...
        }
    },
    # ...
]
```

**Por quê?**: MongoDB usa índices compostos `[user_id, ...]` para performance. Filtro primeiro = mais rápido.

---

### 7. **Não Revelar Informações**

❌ **ERRADO**:
```python
if not transaction:
    return "Transação não encontrada"
else:
    if transaction['user_id'] != user_id:
        return "Transação pertence a outro usuário"  # Revela informação!
```

✅ **CORRETO**:
```python
transaction = repo.find_by_id(id, user_id=user_id)
if not transaction:
    return "Transação não encontrada"  # Não revela se existe ou não
```

**Por quê?**: Evita vazamento de informação sobre existência de dados de outros usuários.

---

## 🔐 Estrutura Preparada para Futuro

### Roles (Papeis)

**Schema atualizado**:
```javascript
{
  _id: ObjectId,
  email: String,
  password_hash: String,
  role: String,              // 'user', 'admin'
  is_active: Boolean,
  created_at: ISODate,
  updated_at: ISODate
}
```

**Uso**:
```python
from core.models.user_model import UserModel

# Verificar permissão
if UserModel.has_permission(user, 'view_all_transactions'):
    # Admin pode ver todas
    pass

# Verificar se é admin
if UserModel.is_admin(user):
    # Ações de admin
    pass
```

---

### Accounts (Contas/Organizações)

**Schema preparado**:
```javascript
{
  _id: ObjectId,
  email: String,
  password_hash: String,
  role: String,
  account_id: ObjectId,      // ID da conta/organização
  is_active: Boolean,
  created_at: ISODate,
  updated_at: ISODate
}
```

**Futuro**: Múltiplos usuários podem pertencer à mesma conta.

**Filtro futuro**:
```python
# Filtrar por account_id também
query = {
    'user_id': ObjectId(user_id),
    'account_id': ObjectId(account_id)  # Futuro
}
```

---

## 📋 Checklist de Segurança

### Em Views
- [x] ✅ user_id sempre de `request.user_mongo['_id']` ou `request.user_id`
- [x] ✅ Nunca aceitar user_id de parâmetros HTTP
- [x] ✅ Validar autenticação antes de processar

### Em Services
- [x] ✅ Validar user_id obrigatório
- [x] ✅ Sempre passar user_id para repositories
- [x] ✅ Não processar sem user_id válido

### Em Repositories
- [x] ✅ Sempre filtrar por user_id em queries
- [x] ✅ Validar user_id em find_by_id
- [x] ✅ user_id obrigatório em create

### Em Agregações MongoDB
- [x] ✅ user_id sempre primeiro no $match
- [x] ✅ Usar índices compostos [user_id, ...]
- [x] ✅ Nunca agregações sem filtro de user_id

---

## 🚨 Ataques Comuns e Proteções

### 1. **IDOR (Insecure Direct Object Reference)**

**Ataque**: Cliente tenta acessar transação de outro usuário:
```
GET /api/transactions/507f1f77bcf86cd799439999
```

**Proteção**:
```python
# Sempre validar user_id na query
transaction = repo.find_by_id(transaction_id, user_id=user_id)
# Retorna None se não pertencer ao usuário
```

---

### 2. **Parameter Tampering**

**Ataque**: Cliente modifica parâmetros:
```
GET /api/dashboard/?user_id=507f1f77bcf86cd799439999
```

**Proteção**:
```python
# Ignorar user_id do request, usar do middleware
user_id = str(request.user_mongo['_id'])  # Sempre do autenticado
```

---

### 3. **NoSQL Injection**

**Ataque**: Cliente tenta injeção NoSQL:
```
GET /api/transactions/?user_id[$ne]=null
```

**Proteção**:
```python
# Sempre converter para ObjectId
user_id = ObjectId(user_id)  # Falha se inválido
# Nunca usar user_id diretamente em queries sem validação
```

---

### 4. **Privilege Escalation**

**Ataque**: Usuário comum tenta acessar funcionalidades de admin.

**Proteção**:
```python
# Verificar role antes de ações sensíveis
if not UserModel.is_admin(user):
    raise PermissionError("Acesso negado")
```

---

## 📊 Validações Implementadas

### TransactionRepository

```python
def create(self, data):
    # ✅ Valida user_id obrigatório
    if 'user_id' not in data:
        raise ValueError("user_id é obrigatório")
    
    # ✅ Converte e valida ObjectId
    data['user_id'] = ObjectId(user_id)

def find_by_id(self, document_id, user_id=None):
    # ✅ Valida user_id na query
    if user_id:
        query['user_id'] = ObjectId(user_id)
```

### DashboardService

```python
def get_dashboard_data(self, user_id, period):
    # ✅ Valida user_id obrigatório
    if not user_id:
        raise ValueError("user_id é obrigatório")
    
    # ✅ Todas as agregações filtram por user_id primeiro
    pipeline = [{
        '$match': {
            'user_id': ObjectId(user_id),  # CRÍTICO
            # ...
        }
    }]
```

---

## 🔍 Auditoria e Logs

Todos os acessos são logados:

```python
# Log de acesso a dados
audit_service.log_action(
    user_id=user_id,
    action='view_dashboard',
    entity='dashboard',
    source='api',
    status='success'
)
```

**Benefício**: Rastreabilidade completa de quem acessou o quê.

---

## ✅ Garantias de Segurança

1. ✅ **Isolamento Total**: Nenhum usuário vê dados de outro
2. ✅ **Validação em Múltiplas Camadas**: Views → Services → Repositories
3. ✅ **Middleware de Segurança**: user_id sempre disponível
4. ✅ **Fail-Fast**: Erros imediatos se user_id inválido
5. ✅ **Índices Otimizados**: Performance sem comprometer segurança
6. ✅ **Auditoria Completa**: Todos os acessos logados
7. ✅ **Preparado para Roles**: Estrutura para admin/user
8. ✅ **Preparado para Accounts**: Estrutura para multi-tenant

---

## 🎯 Boas Práticas

1. ✅ **Sempre validar user_id** antes de queries
2. ✅ **Nunca confiar em dados do cliente** para user_id
3. ✅ **Sempre filtrar por user_id** em queries MongoDB
4. ✅ **Usar índices compostos** [user_id, ...] para performance
5. ✅ **Logar acessos** para auditoria
6. ✅ **Fail-fast** se user_id inválido
7. ✅ **Não revelar informações** sobre existência de dados de outros usuários

---

## 📝 Exemplo Completo de Fluxo Seguro

```python
# 1. View recebe request
def dashboard_api_view(request):
    # 2. Middleware já validou autenticação
    # 3. user_id vem do middleware (seguro)
    user_id = str(request.user_mongo['_id'])
    
    # 4. Service valida user_id
    service = DashboardService()
    data = service.get_dashboard_data(user_id, period)
    # ↑ Service valida user_id obrigatório
    
    # 5. Service chama repository
    # 6. Repository sempre filtra por user_id
    # 7. MongoDB retorna apenas dados do usuário
    # 8. Dados retornados ao cliente
    
    return JsonResponse(data)
```

**Resultado**: Cliente só vê seus próprios dados, sempre.

---

## 🚀 Próximos Passos (Futuro)

### Roles
- [ ] Implementar verificação de roles em views
- [ ] Criar decorator `@require_role('admin')`
- [ ] Adicionar permissões granulares

### Accounts
- [ ] Adicionar account_id ao schema
- [ ] Filtrar por account_id também
- [ ] Suporte a múltiplos usuários por conta

### Auditoria Avançada
- [ ] Alertas para acessos suspeitos
- [ ] Rate limiting por usuário
- [ ] Bloqueio automático após tentativas

