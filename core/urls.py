from django.urls import path
from . import views
from django.views.generic import TemplateView

urlpatterns = [
    path('', views.ana_sayfa, name='ana_sayfa'),
    path('kesfet/', views.kesfet, name='kesfet'),
    # YENİ STATİK SAYFALAR
    path('hakkimizda/', views.hakkimizda, name='hakkimizda'),
    path('nasil-calisir/rozetler/', views.rozetler, name='rozetler'),
    path('iletisim/', views.iletisim, name='iletisim'),
    path('kullanim-rehberi/', views.rehber, name='rehber'),
    path('gizlilik-politikasi/', views.gizlilik, name='gizlilik'),
    path('kullanim-kosullari/', views.kosullar, name='kosullar'),
    path('test-404/', TemplateView.as_view(template_name='core/404.html')),
]