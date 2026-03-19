from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/ayarlar/', views.isletme_ayarlar, name='isletme_ayarlar'),
    # YENİ: Hesap Silme Rotası
    path('dashboard/hesap-sil/', views.hesap_sil, name='hesap_sil'),

    path('dashboard/hizmetler/', views.isletme_hizmetler, name='isletme_hizmetler'),
    path('dashboard/hizmet-duzenle/<int:id>/', views.hizmet_duzenle, name='hizmet_duzenle'),
    path('dashboard/hizmet-sil/<int:id>/', views.hizmet_sil, name='hizmet_sil'),

    path('dashboard/analiz/', views.isletme_analiz, name='isletme_analiz'),

    # ==========================================
    # YENİ: PERSONEL YÖNETİMİ URL'LERİ
    # ==========================================
    path('dashboard/personeller/', views.isletme_personeller, name='isletme_personeller'),
    path('dashboard/personel-sil/<int:id>/', views.personel_sil, name='personel_sil'),
    path('dashboard/personel-durum/<int:id>/', views.personel_durum_degistir, name='personel_durum_degistir'), # YENİ EKLENDİ

    # ==========================================
    # YENİ: KUPON YÖNETİMİ URL'LERİ
    # ==========================================
    path('dashboard/kuponlar/', views.isletme_kuponlar, name='isletme_kuponlar'),
    path('dashboard/kupon-sil/<int:id>/', views.kupon_sil, name='kupon_sil'),

    path('dashboard/musteriler/', views.isletme_musteriler, name='isletme_musteriler'),
    path('dashboard/abonelik/', views.isletme_abonelik, name='isletme_abonelik'),
    path('dashboard/pro-yap/', views.pro_yap, name='pro_yap'),
    path('dashboard/musteriler/indir/', views.musterileri_indir_csv, name='musterileri_indir_csv'),

    # MÜŞTERİ ÖDEME / SİPARİŞ ÖZETİ EKRANI
    path('randevu/odeme-ozeti/<int:randevu_id>/', views.randevu_odeme_ozeti, name='randevu_odeme_ozeti'),
    # YENİ: İyzico Geri Dönüş Rotası
    path('dashboard/randevu/odeme-sonuc/<int:randevu_id>/', views.randevu_odeme_sonuc, name='randevu_odeme_sonuc'),

    path('degerlendir/<uuid:token>/', views.degerlendirme_yap, name='degerlendirme_yap'),

    path('api/available-times/<slug:slug>/', views.get_available_times, name='api_available_times'),

    # DİKKAT: Slug her zaman en altta olmalıdır!
    path('<slug:slug>/', views.isletme_detay, name='isletme_detay'),
]