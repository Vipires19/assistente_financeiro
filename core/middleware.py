"""
Middleware para autenticação via MongoDB.

Localização: core/middleware.py

Este middleware verifica se o usuário está autenticado e adiciona
os dados do usuário ao request.user_mongo para uso nas views.

IMPORTANTE: Este middleware garante isolamento de dados entre usuários.
Sempre verifica user_id antes de permitir acesso a rotas protegidas.
"""
from django.shortcuts import redirect
from django.urls import reverse
from core.services.auth_service import AuthService
from core.services.audit_log_service import AuditLogService
import traceback


class MongoAuthMiddleware:
    """
    Middleware para autenticação customizada com MongoDB.
    
    Adiciona user_mongo ao request se autenticado.
    Protege rotas que não estão na lista de exceções.
    """
    
    # Rotas que não precisam de autenticação
    EXEMPT_PATHS = [
        '/login/',
        '/register/',
        '/logout/',
        '/admin/login/',
        '/static/',
        '/media/',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.auth_service = AuthService()
    
    def __call__(self, request):
        # Verifica se a rota está nas exceções
        path = request.path
        is_exempt = any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS)
        
        # Se não for exceção, verifica autenticação
        if not is_exempt:
            user_id = request.session.get('user_id')
            
            if user_id:
                user = self.auth_service.get_user(user_id)
                if user:
                    request.user_mongo = user
                else:
                    # Usuário não encontrado, limpa sessão
                    request.session.flush()
                    request.user_mongo = None
                    return redirect('core:login')
            else:
                # Não autenticado, redireciona para login
                request.user_mongo = None
                return redirect('core:login')
        else:
            # Rota exceção, apenas verifica se há usuário na sessão
            user_id = request.session.get('user_id')
            if user_id:
                user = self.auth_service.get_user(user_id)
                if user:
                    request.user_mongo = user
                else:
                    request.user_mongo = None
            else:
                request.user_mongo = None
        
        response = self.get_response(request)
        return response

