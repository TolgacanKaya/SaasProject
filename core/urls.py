from django.urls import path
from . import views

urlpatterns = [
    path('', views.ana_sayfa, name='ana_sayfa'),
    path('kesfet/', views.kesfet, name='kesfet'),
    # YENİ STATİK SAYFALAR
    path('hakkimizda/', views.hakkimizda, name='hakkimizda'),
    path('nasil-calisir/rozetler/', views.rozetler, name='rozetler'),
    path('iletisim/', views.iletisim, name='iletisim'),
]