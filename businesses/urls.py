from django.urls import path
from . import views
from .views_gdpr import isletme_veri_export

urlpatterns = [
    path('isletme-sec/', views.isletme_sec, name='isletme_sec'),
    path('yeni-sube/', views.yeni_sube_ekle, name='yeni_sube_ekle'),

    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/ayarlar/', views.isletme_ayarlar, name='isletme_ayarlar'),
    path('dashboard/hizli-kayit/', views.isletme_hizli_kayit, name='isletme_hizli_kayit'),
    # YENİ: Hesap Silme Rotası
    path('dashboard/hesap-sil/', views.hesap_sil, name='hesap_sil'),

    path('dashboard/hizmetler/', views.isletme_hizmetler, name='isletme_hizmetler'),
    path('dashboard/hizmet-duzenle/<int:id>/', views.hizmet_duzenle, name='hizmet_duzenle'),
    path('dashboard/hizmet-sil/<int:id>/', views.hizmet_sil, name='hizmet_sil'),

    path('dashboard/analiz/', views.isletme_analiz, name='isletme_analiz'),
    path('analiz-raporu-indir/', views.analiz_raporu_indir, name='analiz_raporu_indir'),

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
    path('dashboard/verilerimi-indir/', isletme_veri_export, name='isletme_veri_export'),
    path('dashboard/musteriler/engelle/<int:id>/', views.musteri_engelle, name='musteri_engelle'),

    path('giderler/', views.isletme_giderler, name='isletme_giderler'),
    path('gider-raporu-indir/', views.gider_raporu_indir, name='gider_raporu_indir'),

    path('spotify/login/', views.spotify_bagla, name='spotify_bagla'),
    path('spotify/callback/', views.spotify_callback, name='spotify_callback'),

    path('spotify/current-track/', views.spotify_current_track, name='spotify_current_track'),
    path('spotify/skip-track/', views.spotify_skip_track, name='spotify_skip_track'),

    path('spotify/playlists/', views.spotify_get_playlists, name='spotify_get_playlists'),
    path('spotify/play-playlist/', views.spotify_play_playlist, name='spotify_play_playlist'),

    path('spotify/toggle-playback/', views.spotify_toggle_playback, name='spotify_toggle_playback'),
    path('spotify/kopar/', views.spotify_kopar, name='spotify_kopar'),

    path('dashboard/degerlendirmeler/', views.isletme_degerlendirmeler, name='isletme_degerlendirmeler'),

    # Mevcut yollarının arasına şu satırı ekle:
    path('api/canli-arama/', views.canli_arama_api, name='canli_arama_api'),
    path('api/spotify/current-track/<slug:slug>/', views.public_spotify_current_track, name='public_spotify_current_track'),
    path('isletme-spotify/<slug:slug>/', views.public_spotify_jukebox, name='public_spotify_jukebox'),
    path('api/spotify/search/<slug:slug>/', views.public_spotify_search, name='public_spotify_search'),
    path('api/spotify/add-to-queue/<slug:slug>/', views.public_spotify_add_to_queue, name='public_spotify_add_to_queue'),
    path('api/spotify/play-playlist/<slug:slug>/', views.public_spotify_play_playlist, name='public_spotify_play_playlist'),
    path('api/spotify/verify-customer/<slug:slug>/', views.public_spotify_verify_customer, name='public_spotify_verify_customer'),

    path('qr-indir/', views.isletme_qr_indir, name='isletme_qr_indir'),
    path('qr-yazdir/', views.isletme_qr_yazdir, name='isletme_qr_yazdir'),

    path('ayarlar/galeri-sil/<int:id>/', views.galeri_resim_sil, name='galeri_resim_sil'),

    # ==========================================
    # YENİ: PERSONEL SİHİRLİ LİNK ÇALIŞMA PANELİ
    # ==========================================
    path('personel-paneli/<uuid:token>/', views.staff_magic_panel, name='staff_magic_panel'),
    path('personel-paneli/aksiyon/<int:appointment_id>/<str:status_action>/', views.staff_appointment_action, name='staff_appointment_action'),
    path('personel-paneli/sifirla/<int:staff_id>/', views.staff_reset_token, name='staff_reset_token'),

    # DİKKAT: Slug her zaman en altta olmalıdır!
    path('<slug:slug>/rezervasyon/', views.booking_wizard, name='booking_wizard'),
    path('<slug:slug>/yorumlar/', views.isletme_yorumlar, name='isletme_yorumlar'),
    path('<slug:slug>/', views.isletme_detay, name='isletme_detay'),
]