"""
URLs do app core.

Localização: core/urls.py

Define as rotas principais da aplicação.
"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('cadastro/concluido/', views.cadastro_concluido_view, name='cadastro_concluido'),
    path('confirmar-email/', views.confirmar_email_info_view, name='confirmar_email_info'),
    path('verificar-email/<str:token>/', views.verificar_email_view, name='verificar_email'),
    path('verificar-email-sucesso/', views.verificar_email_sucesso_view, name='verificar_email_sucesso'),
    path('email-nao-confirmado/', views.email_nao_confirmado_view, name='email_nao_confirmado'),
    path('reenviar-confirmacao/', views.reenviar_confirmacao_view, name='reenviar_confirmacao'),
    path('recuperar-senha/', views.recuperar_senha_view, name='recuperar_senha'),
    path('resetar-senha/<str:token>/', views.resetar_senha_view, name='resetar_senha'),
    path('senha-redefinida/', views.senha_redefinida_view, name='senha_redefinida'),
    path('planos/', views.planos_view, name='planos'),
    path('planos/assinar/', views.assinar_plano_view, name='assinar_plano'),
    path('assinar/<str:plano>/', views.iniciar_assinatura_view, name='iniciar_assinatura'),
    path('checkout/<str:plano>/', views.pagina_checkout_view, name='pagina_checkout'),
    path('termos-de-uso/', views.termos_de_uso_view, name='termos_de_uso'),
    path('politica-de-privacidade/', views.politica_privacidade_view, name='politica_privacidade'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.index_view, name='dashboard'),
    path('configuracoes/', views.configuracoes_view, name='configuracoes'),
    path('confirmar-novo-email/<str:token>/', views.confirmar_novo_email_view, name='confirmar_novo_email'),
    path('debug-session/', views.debug_session),
]

