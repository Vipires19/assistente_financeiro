"""
URL configuration for dashboard project.

Estrutura de URLs:
- /admin/ - Admin do Django
- /api/ - Endpoints da API (delegado para apps)
- / - URLs principais (delegado para apps)
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),  # URLs da API
    path('', include('core.urls')),     # URLs principais (core)
    path('finance/', include('finance.urls')),  # URLs do finance
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

