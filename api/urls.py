"""
URLs da API.

Localização: api/urls.py

Centraliza todas as rotas da API REST.
"""
from django.urls import path
from core import views as core_views

urlpatterns = [
    path("assinar/<str:plano>/", core_views.api_assinar_plano_view, name="api_assinar_plano"),
]

