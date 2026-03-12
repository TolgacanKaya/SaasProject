from django.urls import path
from . import views

urlpatterns = [
    path('', views.ana_sayfa, name='ana_sayfa'),
    path('kesfet/', views.kesfet, name='kesfet'),
]