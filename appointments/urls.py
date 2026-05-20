from django.urls import path
from . import views

urlpatterns = [
    path('onayla/<int:id>/', views.randevu_onayla, name='randevu_onayla'),
    path('iptal/<int:id>/', views.randevu_iptal, name='randevu_iptal'),
    path('arsiv/', views.isletme_randevular, name='isletme_randevular'),
    path('yonet/<uuid:token>/', views.musteri_randevu_iptal_et, name='musteri_iptal_linki'),

    path('api/service-staffs/<slug:slug>/<int:service_id>/', views.api_service_staffs, name='api_service_staffs'),
    path('randevu-aktar/', views.randevu_aktar, name='randevu_aktar'),

    path('takvim/manuel-ekle/', views.manuel_randevu_olustur, name='manuel_randevu_olustur'),


    path('takvim/', views.takvim_gorunumu, name='takvim_gorunumu'),
    path('api/calendar-events/', views.api_calendar_events, name='api_calendar_events'),
    path('api/calendar-resources/', views.api_calendar_resources, name='api_calendar_resources'),

    # YENİ TAŞINANLAR:
    path('api/available-times/<slug:slug>/', views.get_available_times, name='api_available_times'),
    path('degerlendir/<uuid:token>/', views.degerlendirme_yap, name='degerlendirme_yap'),
    path('google/login/', views.google_takvim_bagla, name='google_takvim_bagla'),
    path('google/callback/', views.google_takvim_callback, name='google_takvim_callback'),
    path('google/kopar/', views.google_takvim_kopar, name='google_takvim_kopar'),
]