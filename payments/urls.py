from django.urls import path
from . import views

urlpatterns = [
    path('premium-satin-al/', views.premium_satin_al, name='premium_satin_al'),
    path('odeme-sonuc/', views.odeme_sonuc, name='odeme_sonuc'),
    path('abonelik-iptal/', views.abonelik_iptal, name='abonelik_iptal'),
    path('abonelik-iptal-vazgec/', views.abonelik_iptal_vazgec, name='abonelik_iptal_vazgec'),
    path('adisyon/<int:adisyon_id>/yazdir/', views.adisyon_yazdir, name='adisyon_yazdir'),
    # VİTRİN BOOST ÖDEMELERİ
    path('boost/', views.boost_satin_al, name='boost_satin_al'),
    path('boost/callback/', views.boost_callback, name='boost_callback'),
    path('boost/clear-session/', views.clear_boost_session, name='clear_boost_session'),
    # YENİ TAŞINANLAR:
    path('randevu/odeme-ozeti/<uuid:token>/', views.randevu_odeme_ozeti, name='randevu_odeme_ozeti'),
    path('dashboard/randevu/odeme-sonuc/<uuid:token>/', views.randevu_odeme_sonuc, name='randevu_odeme_sonuc'),
    path('isletme/iyzico-kayit/', views.isletme_iyzico_kayit, name='isletme_iyzico_kayit'),
]