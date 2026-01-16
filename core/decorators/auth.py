from functools import wraps
from django.shortcuts import redirect
from django.http import JsonResponse

def login_required_mongo(view_func):
    """
    Decorator que exige autenticação via sessão MongoDB.
    
    Para views HTML: redireciona para /login/ se não autenticado
    Para views API (JSON): retorna JSON com erro 401 se não autenticado
    
    NÃO redireciona para /login/ se a rota atual for:
    - /login/
    - /register/
    - /logout/
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Verifica se usuário está autenticado
        user_id = request.session.get('user_id')
        user_mongo = getattr(request, 'user_mongo', None)
        
        if not user_id or not user_mongo:
            # Se for uma requisição API (JSON), retorna JSON
            if request.path.startswith('/finance/api/') or 'application/json' in request.META.get('HTTP_ACCEPT', ''):
                return JsonResponse({
                    'error': 'Não autenticado',
                    'message': 'É necessário fazer login para acessar este recurso'
                }, status=401)
            # Caso contrário, redireciona para login
            return redirect('/login/')
        
        return view_func(request, *args, **kwargs)
    return wrapper


