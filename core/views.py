"""
Views do app core.

Localização: core/views.py

Views são os controllers da aplicação. Elas:
- Recebem requisições HTTP
- Chamam services para lógica de negócio
- Retornam respostas (HTML, JSON, etc.)

NÃO devem conter lógica de negócio, apenas orquestração.
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from core.services.auth_service import AuthService
from core.services.audit_log_service import AuditLogService


def index_view(request):
    """View principal do dashboard (requer autenticação)."""
    # O middleware já adiciona request.user_mongo se autenticado
    if hasattr(request, 'user_mongo') and request.user_mongo:
        return render(request, 'core/dashboard.html', {
            'user': request.user_mongo
        })
    return redirect('core:login')


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    View de login.
    
    GET: Exibe formulário de login
    POST: Processa login
    """
    # Bloqueia acesso se já estiver logado
    if request.session.get('user_id'):
        return redirect('/finance/dashboard/')
    
    audit_service = AuditLogService()
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        
        auth_service = AuthService()
        user = auth_service.authenticate(email, password)
        
        if user:
            # Garante que _id existe
            if '_id' not in user:
                messages.error(request, 'Erro interno: usuário sem ID')
                return render(request, 'core/login.html')
            
            # Salva na sessão
            request.session['user_id'] = str(user['_id'])
            request.session['user_email'] = user['email']
            
            # Loga login bem-sucedido
            audit_service.log_login(
                user_id=str(user['_id']),
                source='dashboard',
                status='success'
            )
            
            messages.success(request, f'Bem-vindo, {user["email"]}!')
            return redirect('/finance/dashboard/')
        else:
            # Loga tentativa de login falha
            # Não temos user_id, então loga sem user_id
            audit_service.log_action(
                user_id=None,
                action='login',
                entity='user',
                source='dashboard',
                status='error',
                payload={'email': email},
                error='Email ou senha incorretos'
            )
            
            messages.error(request, 'Email ou senha incorretos.')
    
    return render(request, 'core/login.html')


@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    View de registro.
    
    GET: Exibe formulário de registro
    POST: Processa registro
    """
    # Se já estiver logado, redireciona
    if hasattr(request, 'user_mongo') and request.user_mongo:
        return redirect('core:index')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        
        if password != password_confirm:
            messages.error(request, 'As senhas não coincidem.')
            return render(request, 'core/register.html')
        
        auth_service = AuthService()
        try:
            user = auth_service.register(email, password)
            # Garante que _id existe antes de salvar na sessão
            if '_id' not in user:
                from django.http import HttpResponseServerError
                return HttpResponseServerError('Erro interno: usuário criado sem ID')
            
            # Salva na sessão
            request.session['user_id'] = str(user['_id'])
            request.session['user_email'] = user['email']
            messages.success(request, 'Conta criada com sucesso!')
            return redirect('core:index')
        except ValueError as e:
            messages.error(request, str(e))
    
    return render(request, 'core/register.html')


def logout_view(request):
    """View de logout."""
    request.session.flush()
    messages.success(request, 'Você saiu com sucesso.')
    return redirect('core:login')

from django.http import HttpResponse

def debug_session(request):
    before = dict(request.session)
    request.session['teste'] = 'ok'
    request.session.modified = True
    after = dict(request.session)

    return HttpResponse(
        f"ANTES: {before}\nDEPOIS: {after}\nSESSION KEY: {request.session.session_key}"
    )
