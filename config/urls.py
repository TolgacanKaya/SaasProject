"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('patron-gizli-giris-404/', admin.site.urls),
    path('hesap/', include('accounts.urls')),


    path('pos/', include('pos.urls')),

    # DİKKAT: path('businesses/', include('businesses.urls')) satırını sildik! Çiftleme yapıyordu.

    path('randevu-yonetimi/', include('appointments.urls')),
    path('odeme/', include('payments.urls')),

    # Kök dizinler en altta olmalı
    path('', include('core.urls')),
    path('', include('businesses.urls')),  # Dashboard ve Slug rotaları buradan çalışacak
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    import debug_toolbar
    urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
