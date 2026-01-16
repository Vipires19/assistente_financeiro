# 🔐 Implementação de Login - Documentação

## ✅ O que foi implementado

### 1. **Repository de Usuário** (`core/repositories/user_repository.py`)
- ✅ CRUD completo de usuários no MongoDB
- ✅ Hash de senha com bcrypt
- ✅ Verificação de senha
- ✅ Índice único no email
- ✅ Métodos: `create()`, `find_by_email()`, `find_by_id()`, `verify_password()`, `update()`

### 2. **Service de Autenticação** (`core/services/auth_service.py`)
- ✅ Registro de novos usuários
- ✅ Autenticação (login)
- ✅ Validações de negócio
- ✅ Busca de usuário por ID
- ✅ Métodos: `register()`, `authenticate()`, `get_user()`

### 3. **Middleware de Autenticação** (`core/middleware.py`)
- ✅ Proteção automática de rotas
- ✅ Exceções para login, register, admin, static/media
- ✅ Adiciona `request.user_mongo` se autenticado
- ✅ Redireciona para login se não autenticado

### 4. **Views** (`core/views.py`)
- ✅ `login_view()` - GET/POST para login
- ✅ `register_view()` - GET/POST para registro
- ✅ `logout_view()` - Logout e limpeza de sessão
- ✅ `index_view()` - Dashboard principal (protegido)

### 5. **Templates HTML** (`templates/core/`)
- ✅ `login.html` - Tela de login responsiva
- ✅ `register.html` - Tela de registro responsiva
- ✅ `dashboard.html` - Dashboard após login
- ✅ `base.html` - Template base com TailwindCSS
- ✅ Design minimalista e profissional
- ✅ Totalmente responsivo (mobile-first)

### 6. **Configurações**
- ✅ Middleware adicionado ao `settings.py`
- ✅ URLs configuradas em `core/urls.py`
- ✅ Dependência `bcrypt` adicionada ao `requirements.txt`

## 📁 Estrutura de Arquivos

```
dashboard/
├── core/
│   ├── repositories/
│   │   └── user_repository.py      # 📦 Repository de usuário
│   ├── services/
│   │   └── auth_service.py         # 💼 Service de autenticação
│   ├── middleware.py                # 🛡️ Middleware de proteção
│   ├── views.py                     # 🎮 Views (login, register, logout)
│   └── urls.py                      # 🔗 URLs
│
└── templates/
    ├── base.html                    # Template base
    └── core/
        ├── login.html               # Tela de login
        ├── register.html            # Tela de registro
        └── dashboard.html           # Dashboard
```

## 🔄 Fluxo de Autenticação

### Login
```
1. Usuário acessa /login/
2. Preenche email e senha
3. POST → login_view()
4. AuthService.authenticate() verifica credenciais
5. UserRepository.verify_password() valida senha (bcrypt)
6. Se válido: salva user_id na sessão
7. Redireciona para /dashboard/
```

### Proteção de Rotas
```
1. Request chega
2. MongoAuthMiddleware verifica se rota está em EXEMPT_PATHS
3. Se não estiver:
   - Verifica user_id na sessão
   - Busca usuário no MongoDB
   - Adiciona request.user_mongo
   - Se não autenticado: redireciona para /login/
4. Se estiver em EXEMPT_PATHS: permite acesso
```

## 🚀 Como Usar

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Configurar MongoDB
Edite o arquivo `.env`:
```env
MONGODB_HOST=mongodb://localhost:27017/
MONGODB_DATABASE=dashboard_db
```

### 3. Executar servidor
```bash
python manage.py runserver
```

### 4. Acessar
- Login: `http://localhost:8000/login/`
- Registro: `http://localhost:8000/register/`
- Dashboard: `http://localhost:8000/` (requer autenticação)

## 📝 Exemplo de Uso no Código

### Em uma View
```python
def minha_view(request):
    # O middleware já adiciona request.user_mongo se autenticado
    if hasattr(request, 'user_mongo') and request.user_mongo:
        user = request.user_mongo
        # user['id'], user['email'], etc.
```

### Criar Usuário Programaticamente
```python
from core.services.auth_service import AuthService

service = AuthService()
user = service.register('user@email.com', 'senha123')
```

### Autenticar Programaticamente
```python
from core.services.auth_service import AuthService

service = AuthService()
user = service.authenticate('user@email.com', 'senha123')
if user:
    # Usuário autenticado
    print(user['email'])
```

## 🔒 Segurança

- ✅ Senhas hasheadas com bcrypt
- ✅ Sessões do Django para autenticação
- ✅ CSRF protection ativado
- ✅ Validação de email único
- ✅ Senha mínima de 6 caracteres
- ✅ Middleware protege rotas automaticamente

## 🎨 Design

- ✅ TailwindCSS via CDN
- ✅ Design minimalista e profissional
- ✅ Responsivo (mobile-first)
- ✅ Gradientes sutis
- ✅ Feedback visual (mensagens de erro/sucesso)
- ✅ Transições suaves

## 📋 Rotas Disponíveis

| Rota | Método | Descrição | Autenticação |
|------|--------|-----------|--------------|
| `/` | GET | Dashboard principal | ✅ Requerida |
| `/login/` | GET/POST | Tela de login | ❌ Pública |
| `/register/` | GET/POST | Tela de registro | ❌ Pública |
| `/logout/` | GET | Logout | ✅ Requerida |
| `/dashboard/` | GET | Dashboard (alias de `/`) | ✅ Requerida |

## 🐛 Troubleshooting

### Erro: "Erro ao conectar ao MongoDB"
- Verifique se o MongoDB está rodando
- Confira as configurações no `.env`

### Erro: "Email já cadastrado"
- O email deve ser único no banco
- Use outro email ou delete o usuário existente

### Redirecionamento infinito
- Verifique se o middleware está configurado corretamente
- Confira se as rotas de login/register estão em EXEMPT_PATHS

## ✨ Próximos Passos (Opcional)

- [ ] Recuperação de senha
- [ ] Lembrar-me (remember me)
- [ ] Verificação de email
- [ ] Rate limiting no login
- [ ] Logs de acesso
- [ ] 2FA (autenticação de dois fatores)

