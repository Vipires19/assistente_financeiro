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
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.index_view, name='dashboard'),
    path('debug-session/', views.debug_session),

]

