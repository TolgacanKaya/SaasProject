from django.urls import path
from . import views

urlpatterns = [
    path('premium-satin-al/', views.premium_satin_al, name='premium_satin_al'),
    path('odeme-sonuc/', views.odeme_sonuc, name='odeme_sonuc'),
]