from django.urls import path
from . import views

urlpatterns = [
    # Ana sayfamızın linki (boş bıraktık ki direkt 127.0.0.1:8000 yazınca açılsın)
    path('', views.ana_sayfa, name='ana_sayfa'),
    path('kesfet/', views.kesfet, name='kesfet'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/ayarlar/', views.isletme_ayarlar, name='isletme_ayarlar'),
    path('dashboard/hizmetler/', views.isletme_hizmetler, name='isletme_hizmetler'),
    path('dashboard/hizmet-sil/<int:id>/', views.hizmet_sil, name='hizmet_sil'),
    path('dashboard/musteriler/', views.isletme_musteriler, name='isletme_musteriler'),
    path('dashboard/randevular/', views.isletme_randevular, name='isletme_randevular'),
    path('dashboard/abonelik/', views.isletme_abonelik, name='isletme_abonelik'),
    path('randevu-onayla/<int:id>/', views.randevu_onayla, name='randevu_onayla'),
    path('randevu-iptal/<int:id>/', views.randevu_iptal, name='randevu_iptal'),
    path('dashboard/pro-yap/', views.pro_yap, name='pro_yap'),
    path('giris/', views.isletme_giris, name='giris'),
    path('cikis/', views.isletme_cikis, name='cikis'),
    path('kayit/', views.isletme_kayit, name='kayit'),
    path('<slug:slug>/', views.isletme_detay, name='isletme_detay'),
]