from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import AsenkronPasswordResetForm  # YENİ: Hızlı formumuzu import ettik!

urlpatterns = [
    path('giris/', views.isletme_giris, name='giris'),
    path('cikis/', views.isletme_cikis, name='cikis'),
    path('kayit/', views.isletme_kayit, name='kayit'),

    # YENİ: ŞİFRE SIFIRLAMA URL'LERİ (Hızlı Form Entegre Edildi)
    path('sifremi-unuttum/', auth_views.PasswordResetView.as_view(
        template_name='accounts/sifre_sifirla.html',
        email_template_name='accounts/sifre_sifirla_email.html',
        html_email_template_name='accounts/sifre_sifirla_email.html',
        form_class=AsenkronPasswordResetForm  # İŞTE SİHİR BURADA: Ekran donmasını engelleyen form!
    ), name='password_reset'),

    path('sifremi-unuttum/mesaj-gonderildi/',
         auth_views.PasswordResetDoneView.as_view(template_name='accounts/sifre_sifirla_gonderildi.html'),
         name='password_reset_done'),
    path('sifre-yenile/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(template_name='accounts/sifre_sifirla_onay.html'),
         name='password_reset_confirm'),
    path('sifre-yenile/basarili/',
         auth_views.PasswordResetCompleteView.as_view(template_name='accounts/sifre_sifirla_tamam.html'),
         name='password_reset_complete'),
]