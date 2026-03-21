from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Appointment
from django.core.paginator import Paginator
from businesses.models import Business
from django.db.models import Case, When, Value, IntegerField
from datetime import timedelta
import threading
from payments.views import iyzico_ucret_iade_et
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# ==========================================
# AKILLI BİLDİRİM SİSTEMİ
# ==========================================
def arka_planda_mail_at(subject, message, from_email, recipient_list, html_message):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=True,
        )
        print(f"📧 [GERÇEK MAIL GÖNDERİLDİ] Kime: {recipient_list[0]}")
    except Exception as e:
        print(f"❌ Mail gönderim hatası: {e}")


def bildirim_gonder(musteri, mesaj, html_mesaj=None):
    temiz_telefon = musteri.phone.replace(" ", "").replace("-", "").replace("(", "").replace(")",
                                                                                             "") if musteri.phone else "Bilinmiyor"
    print(f"📨 [SMS SİMÜLASYONU] Kime: {temiz_telefon} | Mesaj: {mesaj}")

    if musteri.email:
        email_thread = threading.Thread(
            target=arka_planda_mail_at,
            args=(
                'Randevu Bilgilendirmesi | T-Randevu',
                mesaj,
                settings.DEFAULT_FROM_EMAIL,
                [musteri.email],
                html_mesaj
            )
        )
        email_thread.start()

    return True


# ==========================================
# 🔥 GOOGLE TAKVİM BOTU 🔥
# ==========================================
def randevuyu_takvime_ekle(randevu):
    """ Sihirli anahtarı kullanarak Google Takvime randevuyu işler """
    isletme = randevu.business

    # Patron takvimi bağlamamışsa sessizce çık
    if not isletme.google_refresh_token:
        return False

        # 1. Veritabanındaki anahtarları Google'ın anlayacağı formata çeviriyoruz
    creds = Credentials(
        token=isletme.google_access_token,
        refresh_token=isletme.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )

    try:
        # 2. Google Takvim motorunu çalıştır
        service = build('calendar', 'v3', credentials=creds)

        # 3. Randevunun ne kadar süreceğini hesapla
        sure_dk = 60
        if randevu.service and randevu.service.duration:
            if randevu.service.duration_type == 'minutes':
                sure_dk = randevu.service.duration
            elif randevu.service.duration_type == 'hours':
                sure_dk = randevu.service.duration * 60

        bitis_zamani = randevu.date_time + datetime.timedelta(minutes=sure_dk)

        # 4. Takvime eklenecek fiyakalı etiketi (Paketi) hazırla
        event = {
            'summary': f'💇‍♀️ T-Randevu: {randevu.service.name}',
            'location': isletme.address or 'Belirtilmedi',
            'description': f'👤 Müşteri: {randevu.customer.first_name} {randevu.customer.last_name}\n📞 Telefon: {randevu.customer.phone}\n📝 Not: {randevu.customer_note or "Yok"}\n💸 Tutar: {randevu.final_service_price} TL',
            'start': {
                'dateTime': randevu.date_time.isoformat(),
                'timeZone': 'Europe/Istanbul',
            },
            'end': {
                'dateTime': bitis_zamani.isoformat(),
                'timeZone': 'Europe/Istanbul',
            },
            'colorId': '5',  # Google Takvimde dikkat çekici sarı/hardal rengi
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},
                ],
            },
        }

        # 5. ROKETİ FIRLAT!
        service.events().insert(calendarId='primary', body=event).execute()
        return True

    except Exception as e:
        print(f"Google Takvime Eklerken Hata Çıktı: {e}")
        return False


@login_required(login_url="/hesap/giris/")
def randevu_onayla(request, id):
    randevu = get_object_or_404(Appointment, id=id, business__owner=request.user)

    # GÜVENLİK DUVARI: Zaten onaylanmış, iptal edilmiş veya tarihi geçmişse engelle!
    if randevu.status != 'pending':
        messages.error(request, '❌ Sadece bekleyen randevular üzerinde işlem yapabilirsiniz.')
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

    if randevu.date_time < timezone.now():
        messages.error(request, '❌ Tarihi geçmiş randevular üzerinde işlem yapılamaz.')
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

    # HATA 1 ÇÖZÜMÜ: approved yerine confirmed kullanıldı
    randevu.status = 'confirmed'
    randevu.save()

    # ==========================================
    # 🔥 SİHİRLİ DOKUNUŞ: PATRON ONAYLADIĞI AN TAKVİME YAZ!
    # ==========================================
    takvim_sonucu = randevuyu_takvime_ekle(randevu)

    musteri_adi = f"{randevu.customer.first_name} {randevu.customer.last_name}"
    tarih = randevu.date_time.strftime("%d.%m.%Y %H:%M")
    mesaj = f"Sayın {musteri_adi},\n\n{tarih} tarihli randevunuz {randevu.business.name} tarafından ONAYLANMIŞTIR. Bizi tercih ettiğiniz için teşekkürler."
    html_mesaj = render_to_string('businesses/randevu_onay_email.html', {'randevu': randevu})

    bildirim_gonder(randevu.customer, mesaj, html_mesaj)

    # Patronu takvime işlenip işlenmediği konusunda bilgilendir
    if takvim_sonucu:
        messages.success(request, '✅ Randevu onaylandı, müşteriye e-posta gönderildi ve Google Takviminize işlendi!')
    else:
        messages.success(request, '✅ Randevu onaylandı ve müşteriye bildirildi.')

    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


# ==========================================
# İŞLETME SAHİBİ RANDEVUYU İPTAL EDİYOR
# ==========================================
@login_required(login_url="/hesap/giris/")
def randevu_iptal(request, id):
    randevu = get_object_or_404(Appointment, id=id, business__owner=request.user)

    # GÜVENLİK DUVARI: Zaten kapatılmış veya tarihi geçmişse engelle!
    if randevu.status in ['cancelled', 'customer_cancelled', 'completed']:
        messages.error(request, '❌ Bu randevu zaten kapatılmış veya iptal edilmiş.')
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

    if randevu.date_time < timezone.now():
        messages.error(request, '❌ Tarihi geçmiş randevuları iptal edemezsiniz.')
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

    # ==========================================
    # 🔥 IYZICO OTOMATİK İADE (İŞLETME İPTAL EDERSE) 🔥
    # ==========================================
    # İşletme iptal ediyorsa, 24 saat kuralı aranmaz, müşteri mağdur olmasın diye direkt iade edilir.
    if randevu.is_paid and randevu.iyzico_transaction_id:
        basarili_mi, iade_mesaji = iyzico_ucret_iade_et(request, randevu)

        if basarili_mi:
            randevu.status = 'cancelled'
            randevu.save()
            messages.success(request, f"✅ Randevu iptal edildi. {iade_mesaji}")
        else:
            # İade başarısızsa randevuyu iptal etme, işletmeyi uyar
            messages.error(request, f"🚨 İptal Başarısız! Ücret iadesi yapılamadı: {iade_mesaji}")
            return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
    else:
        # Ücretsiz veya ödenmemiş bir randevuysa direkt iptal et
        randevu.status = 'cancelled'
        randevu.save()
        messages.success(request, "✅ Randevu başarıyla iptal edildi.")

    # Müşteriye bilgi maili/sms at
    musteri_adi = f"{randevu.customer.first_name} {randevu.customer.last_name}"
    mesaj = f"Sayın {musteri_adi},\n\n{randevu.business.name} işletmesindeki randevunuz maalesef İPTAL edilmiştir. Ücret iadeniz kartınıza yansıtılacaktır. Detaylı bilgi için işletme ile ({randevu.business.phone}) iletişime geçebilirsiniz."
    html_mesaj = render_to_string('businesses/randevu_iptal_email.html', {'randevu': randevu})

    bildirim_gonder(randevu.customer, mesaj, html_mesaj)

    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


@login_required(login_url='/hesap/giris/')
def isletme_randevular(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect('kayit')

    now = timezone.now()

    # HATA 1 ÇÖZÜMÜ: Sadece 'confirmed' olarak düzeltildi
    bir_saat_once = now - timedelta(hours=1)
    isletme.appointments.filter(
        status='confirmed',
        date_time__lt=bir_saat_once
    ).update(status='completed')

    # AKILLI SIRALAMA ALGORİTMASI
    tum_randevular_list = isletme.appointments.all().annotate(
        sira=Case(
            When(date_time__gte=now, status='pending', then=Value(1)),
            When(date_time__gte=now, status='confirmed', then=Value(2)),  # Sadece confirmed
            When(date_time__lt=now, then=Value(3)),
            When(status='completed', then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
    ).order_by('sira', 'date_time')

    paginator = Paginator(tum_randevular_list, 10)
    page = request.GET.get('page')
    randevular = paginator.get_page(page)

    context = {
        "isletme": isletme,
        "randevular": randevular,
        "simdi": now,
    }

    return render(request, 'appointments/isletme_randevular.html', context)


# ==========================================
# MÜŞTERİ KENDİ RANDEVUSUNU İPTAL EDİYOR (MAİL LİNKİNDEN)
# ==========================================
def musteri_randevu_iptal_et(request, token):
    randevu = Appointment.objects.filter(cancel_token=token).last()

    if not randevu:
        messages.error(request, "Bu iptal linki geçersiz veya süresi dolmuş.")
        return redirect('dashboard')

    if randevu.status in ['cancelled', 'customer_cancelled']:
        messages.error(request, "Bu randevu zaten iptal edilmiş.")
        return render(request, 'businesses/islem_tamam.html', {'randevu': randevu})

    if randevu.status == 'completed':
        messages.error(request, "Tamamlanmış bir randevuyu iptal edemezsiniz.")
        return render(request, 'businesses/islem_tamam.html', {'randevu': randevu})

    now = timezone.now()
    kalan_sure = randevu.date_time - now

    # Müşteri iptali için 24 saat kuralı
    iptal_edilebilir_mi = kalan_sure.total_seconds() > 86400

    if request.method == 'POST':
        if iptal_edilebilir_mi:
            # ==========================================
            # 🔥 IYZICO OTOMATİK İADE (MÜŞTERİ İPTAL EDERSE) 🔥
            # ==========================================
            if randevu.is_paid and randevu.iyzico_transaction_id:
                basarili_mi, iade_mesaji = iyzico_ucret_iade_et(request, randevu)

                if basarili_mi:
                    randevu.status = 'customer_cancelled'
                    randevu.save()
                    messages.success(request, f"Randevunuz başarıyla iptal edildi. {iade_mesaji}")
                else:
                    messages.error(request, f"Sistem kaynaklı bir sorun oluştu: {iade_mesaji}")
                    return render(request, 'appointments/musteri_iptal_onay.html', {
                        'randevu': randevu,
                        'iptal_edilebilir_mi': True,
                        'kalan_saat': int(kalan_sure.total_seconds() / 3600)
                    })
            else:
                randevu.status = 'customer_cancelled'
                randevu.save()
                messages.success(request, "Randevunuz başarıyla iptal edildi.")

            return render(request, 'businesses/islem_tamam.html', {'randevu': randevu, 'is_cancel': True})
        else:
            messages.error(request,
                           "Kurallarımız gereği randevunuza 24 saatten az kala iptal işlemi ve ücret iadesi yapılamaz.")

    return render(request, 'appointments/musteri_iptal_onay.html', {
        'randevu': randevu,
        'iptal_edilebilir_mi': iptal_edilebilir_mi,
        'kalan_saat': int(kalan_sure.total_seconds() / 3600) if kalan_sure.total_seconds() > 0 else 0
    })