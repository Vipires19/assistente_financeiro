from django.http import JsonResponse
from core.repositories.user_repository import UserRepository
from bson import ObjectId


class MongoAuthMiddleware:
    """
    Middleware de autenticação via MongoDB.
    
    Injeta o usuário autenticado no request como request.user_mongo
    baseado na sessão do Django.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.user_repo = UserRepository()
        
        # Rotas que não precisam de autenticação
        self.EXEMPT_PATHS = [
            '/login/',
            '/register/',
            '/confirmar-email/',
            '/verificar-email/',
            '/email-nao-confirmado/',
            '/reenviar-confirmacao/',
            '/verificar-email-sucesso/',
            '/planos/',
            '/recuperar-senha/',
            '/resetar-senha/',
            '/senha-redefinida/',
            '/termos-de-uso/',
            '/politica-de-privacidade/',
            '/logout/',
            '/admin/',
        ]

    def __call__(self, request):
        # Verifica se a rota é pública
        path = request.path
        is_exempt = any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS)
        
        # Verifica se é uma requisição de API (JSON)
        is_api_request = path.startswith('/finance/api/') or 'application/json' in request.META.get('HTTP_ACCEPT', '')
        
        # Inicializa user_mongo como None
        request.user_mongo = None
        
        # Se não for rota pública, tenta obter usuário da sessão
        if not is_exempt:
            user_id = request.session.get('user_id')
            if user_id:
                try:
                    user = self.user_repo.find_by_id(user_id)
                    if user:
                        request.user_mongo = user
                    else:
                        # Usuário não encontrado, limpa sessão
                        request.user_mongo = None
                        if 'user_id' in request.session:
                            del request.session['user_id']
                except Exception:
                    # Se houver erro ao buscar usuário, limpa sessão
                    request.user_mongo = None
                    if 'user_id' in request.session:
                        del request.session['user_id']
        else:
            # Rota pública, mas ainda tenta obter usuário se houver sessão
            user_id = request.session.get('user_id')
            if user_id:
                try:
                    user = self.user_repo.find_by_id(user_id)
                    if user:
                        request.user_mongo = user
                except Exception:
                    request.user_mongo = None
        
        response = self.get_response(request)
        return response
