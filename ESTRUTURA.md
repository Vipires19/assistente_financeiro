# 📍 Onde Cada Parte Fica - Guia Rápido

## ⚙️ Settings
**Localização**: `dashboard/settings.py`

Aqui ficam todas as configurações do projeto:
- Configuração do MongoDB em `MONGODB_SETTINGS`
- Apps instalados (`INSTALLED_APPS`)
- Middlewares
- Configurações de static files, media, etc.

```python
MONGODB_SETTINGS = {
    'host': 'mongodb://localhost:27017/',
    'database': 'dashboard_db',
    ...
}
```

---

## 🔗 URLs
**Localização**: 
- `dashboard/urls.py` - URLs principais (rota do projeto)
- `app/urls.py` - URLs de cada app (ex: `core/urls.py`, `finance/urls.py`)

**Estrutura**:
```
dashboard/urls.py
  ├── /admin/ → Admin do Django
  ├── /api/ → api/urls.py
  ├── / → core/urls.py
  └── /finance/ → finance/urls.py
```

**Exemplo**:
```python
# dashboard/urls.py
urlpatterns = [
    path('finance/', include('finance.urls')),  # Delega para finance
]

# finance/urls.py
urlpatterns = [
    path('', views.index_view),  # /finance/
]
```

---

## 📦 Repositories
**Localização**: `app/repositories/`

Cada app tem sua pasta de repositories:
- `core/repositories/` - Repositories base/compartilhados
- `finance/repositories/` - Repositories específicos do finance

**Responsabilidade**: Acesso direto ao MongoDB (camada de dados)

**Exemplo**:
```python
# finance/repositories/transaction_repository.py
class TransactionRepository(BaseRepository):
    def find_by_user(self, user_id):
        return self.find_many({'user_id': ObjectId(user_id)})
```

---

## 💼 Services
**Localização**: `app/services/`

Cada app tem sua pasta de services:
- `finance/services/` - Services do módulo finance

**Responsabilidade**: Lógica de negócio (validações, regras, orquestração)

**Exemplo**:
```python
# finance/services/transaction_service.py
class TransactionService:
    def create_transaction(self, user_id, amount, description):
        # Validações de negócio
        if amount <= 0:
            raise ValueError("Valor inválido")
        
        # Usa repository para persistir
        return self.repo.create({...})
```

---

## 🔌 Database (Conexão MongoDB)
**Localização**: `core/database.py`

Conexão centralizada com MongoDB. Todos os repositories usam esta conexão.

**Uso**:
```python
from core.database import get_database
db = get_database()
collection = db['minha_collection']
```

---

## 🎮 Views
**Localização**: `app/views.py`

Cada app tem seu arquivo `views.py`:
- `core/views.py` - Views do core
- `finance/views.py` - Views do finance

**Responsabilidade**: Controllers HTTP (recebem requests, chamam services, retornam responses)

**Exemplo**:
```python
# finance/views.py
def create_transaction_view(request):
    service = TransactionService()
    transaction = service.create_transaction(...)
    return JsonResponse(transaction)
```

---

## 🔄 Fluxo de Dados

```
HTTP Request
    ↓
View (app/views.py)
    ↓
Service (app/services/)
    ↓ (validações, regras de negócio)
Repository (app/repositories/)
    ↓ (queries MongoDB)
MongoDB
```

---

## 📁 Estrutura Completa

```
dashboard/
├── dashboard/
│   ├── settings.py         ⚙️ Configurações (MongoDB aqui)
│   └── urls.py            🔗 URLs principais
│
├── core/
│   ├── database.py        🔌 Conexão MongoDB
│   ├── repositories/      📦 Repositories base
│   ├── urls.py            🔗 URLs do core
│   └── views.py           🎮 Views do core
│
└── finance/
    ├── repositories/      📦 Repositories específicos
    ├── services/          💼 Services (lógica de negócio)
    ├── urls.py            🔗 URLs do finance
    └── views.py           🎮 Views do finance
```

---

## ✅ Regras de Ouro

1. **Repositories** → Apenas acesso a dados (MongoDB)
2. **Services** → Lógica de negócio (NÃO acessam MongoDB diretamente)
3. **Views** → Apenas orquestração (chamam services)
4. **Database** → Centralizado em `core/database.py`

