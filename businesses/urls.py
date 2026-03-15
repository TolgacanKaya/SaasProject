from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/ayarlar/', views.isletme_ayarlar, name='isletme_ayarlar'),
    path('dashboard/hizmetler/', views.isletme_hizmetler, name='isletme_hizmetler'),
    path('dashboard/hizmet-sil/<int:id>/', views.hizmet_sil, name='hizmet_sil'),
    path('dashboard/musteriler/', views.isletme_musteriler, name='isletme_musteriler'),
    path('dashboard/abonelik/', views.isletme_abonelik, name='isletme_abonelik'),
    path('dashboard/pro-yap/', views.pro_yap, name='pro_yap'),
    path('dashboard/musteriler/indir/', views.musterileri_indir_csv, name='musterileri_indir_csv'),
    path('degerlendir/<uuid:token>/', views.degerlendirme_yap, name='degerlendirme_yap'),
    # DİKKAT: Slug her zaman en altta olmalıdır!
    path('<slug:slug>/', views.isletme_detay, name='isletme_detay'),
]