from django.urls import path
from . import views

urlpatterns = [
    path('urunler/', views.isletme_urunler, name='isletme_urunler'),
    path('dashboard/adisyonlar/', views.isletme_adisyonlar, name='isletme_adisyonlar'),
    path('dashboard/adisyonlar/indir/', views.adisyon_indir_csv, name='adisyon_indir_csv'),
    path('adisyon/<int:randevu_id>/', views.adisyon_detay, name='adisyon_detay'),
]