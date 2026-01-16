# 💰 Financeiro - Dashboard Financeiro com Django e MongoDB

Projeto Django configurado para uso com MongoDB, sem ORM relacional.
Sistema completo de gestão financeira com dashboard, relatórios e auditoria.

## 🏗️ Estrutura do Projeto

```
financeiro/
├── dashboard/              # Configurações do projeto Django
│   ├── settings.py         # ⚙️ Configurações (inclui MongoDB)
│   ├── urls.py            # 🔗 URLs principais
│   ├── wsgi.py
│   └── asgi.py
│
├── core/                   # App core (funcionalidades base)
│   ├── database.py        # 🔌 Conexão MongoDB (centralizada)
│   ├── repositories/      # 📦 Repositories base
│   │   └── base_repository.py
│   ├── urls.py            # 🔗 URLs do core
│   ├── views.py           # 🎮 Views do core
│   └── services/          # (opcional, se necessário)
│
├── finance/                # App finance (módulo financeiro)
│   ├── repositories/      # 📦 Repositories específicos
│   │   └── transaction_repository.py
│   ├── services/          # 💼 Services (lógica de negócio)
│   │   └── transaction_service.py
│   ├── urls.py            # 🔗 URLs do finance
│   └── views.py           # 🎮 Views do finance
│
└── api/                    # API REST (opcional)
    └── urls.py            # 🔗 URLs da API
```

## 📍 Onde Cada Parte Fica

### ⚙️ **Settings** (`financeiro/dashboard/settings.py`)
- Configurações gerais do Django
- Configuração do MongoDB em `MONGODB_SETTINGS`
- Apps instalados (`INSTALLED_APPS`)
- Middlewares
- Configurações de static files, media, etc.

### 🔗 **URLs** (`financeiro/dashboard/urls.py` e `app/urls.py`)
- **`dashboard/urls.py`**: URLs principais do projeto
  - Delega para apps: `path('finance/', include('finance.urls'))`
- **`app/urls.py`**: URLs específicas de cada app
  - Exemplo: `finance/urls.py` define rotas do módulo finance

### 📦 **Repositories** (`app/repositories/`)
- **Localização**: Cada app tem sua pasta `repositories/`
- **Responsabilidade**: Acesso direto ao MongoDB
- **Exemplo**: 
  - `core/repositories/base_repository.py` - Repository base
  - `finance/repositories/transaction_repository.py` - Repository de transações
- **Uso**: Encapsula operações CRUD e queries específicas

### 💼 **Services** (`app/services/`)
- **Localização**: Cada app tem sua pasta `services/`
- **Responsabilidade**: Lógica de negócio
- **Exemplo**: 
  - `finance/services/transaction_service.py` - Lógica de transações
- **Uso**: 
  - Validações de negócio
  - Orquestração de repositories
  - Transformações de dados
  - **NÃO** acessa MongoDB diretamente, apenas via repositories

### 🔌 **Database** (`core/database.py`)
- **Localização**: `core/database.py`
- **Responsabilidade**: Conexão centralizada com MongoDB
- **Uso**: Importado por todos os repositories
  ```python
  from core.database import get_database
  db = get_database()
  ```

### 🎮 **Views** (`app/views.py`)
- **Localização**: Cada app tem seu `views.py`
- **Responsabilidade**: Controllers HTTP
- **Uso**: 
  - Recebem requisições
  - Chamam services
  - Retornam respostas
  - **NÃO** contêm lógica de negócio

## 🔄 Fluxo de Dados

```
Request → View → Service → Repository → MongoDB
                ↓
         (validações, regras de negócio)
                ↓
         (queries, CRUD)
```

## 🚀 Instalação

1. **Instale as dependências:**
```bash
pip install -r requirements.txt
```

2. **Configure o MongoDB no `.env`:**
```env
MONGODB_HOST=mongodb://localhost:27017/
MONGODB_DATABASE=financeiro_db
MONGODB_USERNAME=
MONGODB_PASSWORD=
```

3. **Execute o servidor:**
```bash
python manage.py runserver
```

## 📝 Exemplo de Uso

### Criando um Repository

```python
# finance/repositories/transaction_repository.py
from core.repositories.base_repository import BaseRepository

class TransactionRepository(BaseRepository):
    def __init__(self):
        super().__init__('transactions')
    
    def find_by_user(self, user_id: str):
        return self.find_many({'user_id': ObjectId(user_id)})
```

### Criando um Service

```python
# finance/services/transaction_service.py
from finance.repositories.transaction_repository import TransactionRepository

class TransactionService:
    def __init__(self):
        self.repo = TransactionRepository()
    
    def create_transaction(self, user_id, amount, description):
        # Validações
        if amount <= 0:
            raise ValueError("Valor inválido")
        
        # Usa repository
        return self.repo.create({
            'user_id': ObjectId(user_id),
            'amount': amount,
            'description': description
        })
```

### Usando em uma View

```python
# finance/views.py
from finance.services.transaction_service import TransactionService

def create_transaction_view(request):
    service = TransactionService()
    transaction = service.create_transaction(
        user_id='...',
        amount=100.50,
        description='Compra'
    )
    return JsonResponse(transaction)
```

## 🎯 Princípios

1. **Separação de Responsabilidades**
   - Repositories: Acesso a dados
   - Services: Lógica de negócio
   - Views: Controllers HTTP

2. **Sem ORM Relacional**
   - Acesso direto ao MongoDB via pymongo
   - Repositories encapsulam queries

3. **Arquitetura Limpa**
   - Fácil de testar
   - Fácil de evoluir
   - Código organizado

