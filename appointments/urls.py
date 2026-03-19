from django.urls import path
from . import views

urlpatterns = [
    path('onayla/<int:id>/', views.randevu_onayla, name='randevu_onayla'),
    path('iptal/<int:id>/', views.randevu_iptal, name='randevu_iptal'),
    path('arsiv/', views.isletme_randevular, name='isletme_randevular'),
    path('yonet/<uuid:token>/', views.musteri_randevu_iptal_et, name='musteri_iptal_linki'),
]