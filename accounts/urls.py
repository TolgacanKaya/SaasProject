from django.urls import path
from . import views

urlpatterns = [
    path('giris/', views.isletme_giris, name='giris'),
    path('cikis/', views.isletme_cikis, name='cikis'),
    path('kayit/', views.isletme_kayit, name='kayit'),
]