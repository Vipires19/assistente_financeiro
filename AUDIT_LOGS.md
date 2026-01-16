# 📋 Sistema de Logs e Auditoria - Documentação

## 🎯 Visão Geral

Sistema completo de logs e auditoria para rastrear todas as ações importantes no dashboard financeiro.

**Localização**: `core/repositories/audit_log_repository.py` e `core/services/audit_log_service.py`

---

## 📊 Schema da Collection

### Collection: `audit_logs`

```javascript
{
  _id: ObjectId,
  user_id: ObjectId,           // ID do usuário (null para ações do sistema)
  action: String,              // 'login', 'create_transaction', 'generate_report', 'error'
  entity: String,              // 'user', 'transaction', 'report', 'system'
  entity_id: String,           // ID da entidade (opcional)
  payload: Object,             // Dados adicionais
  source: String,              // 'dashboard', 'api', 'agent'
  status: String,              // 'success', 'error'
  error: String,               // Stacktrace resumido (se status = 'error')
  created_at: ISODate
}
```

### Índices Criados

- `user_id` - Filtros por usuário
- `[user_id, created_at]` (desc) - Ordenação e filtros por período
- `action` - Filtros por tipo de ação
- `[user_id, action]` - Análises por usuário e ação
- `status` - Filtros por status (sucesso/erro)
- `created_at` - Filtros globais por data
- `source` - Filtros por origem

---

## 🔧 Componentes

### 1. AuditLogRepository

**Localização**: `core/repositories/audit_log_repository.py`

Repository para operações com a collection `audit_logs`.

**Métodos**:
- `create(data)` - Cria novo log
- `find_by_user(user_id, limit, skip)` - Busca logs de um usuário
- `find_by_action(action, limit, skip)` - Busca logs por ação
- `find_errors(user_id, limit, skip)` - Busca apenas erros

---

### 2. AuditLogService

**Localização**: `core/services/audit_log_service.py`

Service para gerenciar logs de auditoria.

**Métodos principais**:
- `log_action()` - Log genérico
- `log_login()` - Log de login
- `log_transaction()` - Log de transações
- `log_report()` - Log de relatórios
- `log_error()` - Log de erros
- `get_user_logs()` - Busca logs de usuário
- `get_errors()` - Busca erros

---

### 3. Decorators

**Localização**: `core/decorators.py`

Decorators para logar ações automaticamente.

#### `@audit_log(action, entity, source)`

```python
@audit_log(action='create_transaction', entity='transaction', source='api')
def create_transaction_view(request):
    ...
```

#### `@log_action(action, entity, source, get_user_id, get_entity_id, get_payload)`

Decorator mais flexível com funções customizadas para extrair dados.

---

### 4. ExceptionLoggingMiddleware

**Localização**: `core/middleware/exception_logging_middleware.py`

Middleware que captura exceções não tratadas e as loga automaticamente.

---

## 📝 Ações Logadas Automaticamente

### 1. Login

**Onde**: `core/views.py` - `login_view()`

**Logado**:
- ✅ Login bem-sucedido
- ✅ Tentativas de login falhas

**Exemplo**:
```python
audit_service.log_login(
    user_id='...',
    source='dashboard',
    status='success'
)
```

---

### 2. Criação de Transações

**Onde**: `finance/services/transaction_service.py` - `create_transaction()`

**Logado**:
- ✅ Criação bem-sucedida
- ✅ Erros na criação

**Exemplo**:
```python
audit_service.log_transaction(
    user_id='...',
    action='create_transaction',
    transaction_id='...',
    source='api',
    status='success',
    payload={'type': 'expense', 'value': 100.50}
)
```

---

### 3. Geração de Relatórios

**Onde**: `finance/services/report_service.py` - `generate_text_report()`

**Logado**:
- ✅ Geração bem-sucedida
- ✅ Erros na geração

**Exemplo**:
```python
audit_service.log_report(
    user_id='...',
    report_type='text',
    source='dashboard',
    status='success',
    payload={'period': 'mensal'}
)
```

---

### 4. Erros Não Tratados

**Onde**: `core/middleware/exception_logging_middleware.py`

**Logado**:
- ✅ Todas as exceções não tratadas
- ✅ Stacktrace resumido
- ✅ Path, method, tipo de exceção

**Exemplo**:
```python
audit_service.log_error(
    user_id='...',
    action='unhandled_exception',
    entity='system',
    error='Traceback...',
    source='api',
    payload={'path': '/api/...', 'method': 'GET'}
)
```

---

## 🚀 Exemplos de Uso

### Log Manual

```python
from core.services.audit_log_service import AuditLogService

service = AuditLogService()

# Log de ação genérica
service.log_action(
    user_id='507f1f77bcf86cd799439011',
    action='export_data',
    entity='transaction',
    source='dashboard',
    status='success',
    payload={'format': 'csv', 'count': 150}
)

# Log de erro
service.log_error(
    user_id='507f1f77bcf86cd799439011',
    action='process_payment',
    entity='transaction',
    error='Payment gateway timeout',
    source='api'
)
```

### Usando Decorator

```python
from core.decorators import audit_log

@audit_log(action='delete_transaction', entity='transaction', source='api')
def delete_transaction_view(request, transaction_id):
    # Código da view
    # Log será criado automaticamente
    pass
```

### Buscar Logs

```python
from core.services.audit_log_service import AuditLogService

service = AuditLogService()

# Logs de um usuário
logs = service.get_user_logs(user_id='...', limit=50)

# Apenas erros
errors = service.get_errors(user_id='...', limit=20)
```

---

## 📊 Queries Úteis

### Logs de um usuário no último mês

```python
from datetime import datetime, timedelta
from core.repositories.audit_log_repository import AuditLogRepository

repo = AuditLogRepository()
start_date = datetime.utcnow() - timedelta(days=30)

logs = repo.find_many(
    query={
        'user_id': ObjectId('...'),
        'created_at': {'$gte': start_date}
    },
    limit=100,
    sort=('created_at', -1)
)
```

### Todas as tentativas de login falhas

```python
logs = repo.find_many(
    query={
        'action': 'login',
        'status': 'error'
    },
    limit=100
)
```

### Erros do sistema

```python
errors = repo.find_errors(user_id=None, limit=50)
```

---

## 🔍 Análises Possíveis

### 1. Tentativas de Login Suspeitas

```python
# Múltiplas tentativas falhas do mesmo IP/email
failed_logins = repo.find_many(
    query={
        'action': 'login',
        'status': 'error',
        'created_at': {'$gte': datetime.utcnow() - timedelta(hours=1)}
    }
)
```

### 2. Atividade por Usuário

```python
# Ações mais comuns de um usuário
pipeline = [
    {'$match': {'user_id': ObjectId('...')}},
    {'$group': {'_id': '$action', 'count': {'$sum': 1}}},
    {'$sort': {'count': -1}}
]
```

### 3. Taxa de Erros

```python
# Percentual de erros vs sucessos
total = repo.count({})
errors = repo.count({'status': 'error'})
error_rate = (errors / total) * 100
```

---

## ⚙️ Configuração

### Middleware

Adicionado em `settings.py`:

```python
MIDDLEWARE = [
    ...
    'core.middleware.exception_logging_middleware.ExceptionLoggingMiddleware',
]
```

**Importante**: Deve ser adicionado **após** outros middlewares para capturar exceções.

---

## ✅ Integrações Automáticas

### Já Implementadas

- ✅ Login (sucesso e falha)
- ✅ Criação de transações (sucesso e erro)
- ✅ Geração de relatórios (sucesso e erro)
- ✅ Exceções não tratadas (middleware)

### Próximas Integrações (Futuro)

- [ ] Atualização de transações
- [ ] Exclusão de transações
- [ ] Alteração de senha
- [ ] Exportação de dados
- [ ] Ações administrativas

---

## 📈 Performance

### Índices Otimizados

- Queries por usuário: ~2-10ms
- Queries por ação: ~5-15ms
- Queries de erros: ~5-20ms
- Agregações: ~10-50ms

### Tamanho dos Logs

- Log médio: ~500 bytes
- 10.000 logs: ~5 MB
- Rotação recomendada: Mensal ou quando > 1GB

---

## 🔒 Segurança

- ✅ Logs não contêm senhas
- ✅ Stacktraces limitados a 500-1000 caracteres
- ✅ Payloads sanitizados (sem dados sensíveis)
- ✅ Índices otimizados para queries rápidas

---

## 📝 Boas Práticas

1. ✅ **Sempre logar ações importantes**
2. ✅ **Incluir contexto no payload**
3. ✅ **Limitar tamanho de stacktraces**
4. ✅ **Não logar dados sensíveis**
5. ✅ **Usar decorators quando possível**
6. ✅ **Rotacionar logs periodicamente**

---

## 🐛 Troubleshooting

### Logs não aparecem

- Verifique conexão com MongoDB
- Confirme que índices foram criados
- Verifique console para erros

### Performance lenta

- Verifique índices
- Limite resultados com paginação
- Considere rotacionar logs antigos

### Stacktraces muito grandes

- Já limitados a 500-1000 caracteres
- Ajuste em `_format_error()` se necessário

