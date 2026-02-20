"""
Context processors do app core.

Disponibilizam variáveis globais para templates (ex.: base_dashboard).
O plano do usuário vem do MongoDB (request.user_mongo), não do model User do Django.
"""


def plano_usuario(request):
    """
    Injeta no contexto de todos os templates:
    - plano: valor do banco (trial, mensal, anual, sem_plano)
    - data_vencimento_plano: data de vencimento para badge trial (ou None)
    - user_nome: nome do usuário (header)
    - user_profile_image: caminho da foto de perfil (header)

    Assim o badge da sidebar e o avatar do header refletem o banco.
    """
    plano = 'sem_plano'
    data_vencimento_plano = None
    user_nome = None
    user_profile_image = None

    if getattr(request, 'user_mongo', None):
        usuario = request.user_mongo
        assinatura = usuario.get('assinatura') or {}
        plano = assinatura.get('plano') or usuario.get('plano') or 'sem_plano'
        data_vencimento_plano = (
            assinatura.get('proximo_vencimento')
            or assinatura.get('fim')
            or usuario.get('data_vencimento_plano')
        )
        user_nome = usuario.get('nome') or usuario.get('email') or 'Usuário'
        user_profile_image = usuario.get('profile_image')

    return {
        'plano': plano,
        'data_vencimento_plano': data_vencimento_plano,
        'user_nome': user_nome,
        'user_profile_image': user_profile_image,
    }
