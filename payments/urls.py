from django.urls import path
from . import views

urlpatterns = [
    path('premium-satin-al/', views.premium_satin_al, name='premium_satin_al'),
    path('odeme-sonuc/', views.odeme_sonuc, name='odeme_sonuc'),
    path('abonelik-iptal/', views.abonelik_iptal, name='abonelik_iptal'),
    path('abonelik-iptal-vazgec/', views.abonelik_iptal_vazgec, name='abonelik_iptal_vazgec'),
]