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
from decimal import Decimal
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
from django.http import JsonResponse
from google_auth_oauthlib.flow import Flow
from businesses.models import Service, Review, Staff, Business, Customer
from django.urls import reverse
from businesses.views import get_aktif_isletme


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
        try:
            from appointments.tasks import send_email_task
            send_email_task.delay(
                'Randevu Bilgilendirmesi | KobiRandevu',
                mesaj,
                [musteri.email],
                settings.DEFAULT_FROM_EMAIL,
                html_mesaj
            )
        except Exception as e:
            print(f"HATA: Celery bildirim_gonder tetiklenemedi: {e}")

    return True


# ==========================================
# 🔥 GOOGLE TAKVİM BOTU 🔥
# ==========================================
def randevuyu_takvime_ekle(randevu):
    """ Sihirli anahtarı kullanarak Google Takvime randevuyu işler """
    isletme = randevu.business

    # 🔥 YENİ GÜVENLİK: Eğer işletme Premium değilse takvim senkronizasyonunu anında durdur!
    if not isletme.is_premium:
        return False

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
            'summary': f'💇‍♀️ KobiRandevu: {randevu.service.name}',
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
        # Token süresi dolmuş olabilir, yenilemeyi deneyelim
        try:
            from google.auth.transport.requests import Request
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                isletme.google_access_token = creds.token
                isletme.google_token_expiry = creds.expiry
                isletme.save()
                
                # Yeni token ile tekrar dene
                service = build('calendar', 'v3', credentials=creds)
                service.events().insert(calendarId='primary', body=event).execute()
                return True
        except Exception as re:
            print(f"Google Token Yenileme ve Senkronizasyon Hatası: {re}")
            
        print(f"Google Takvime Eklerken Hata Çıktı: {e}")
        return False


@login_required(login_url="/hesap/giris/")
def randevu_onayla(request, id):
    isletme = get_aktif_isletme(request)
    randevu = get_object_or_404(Appointment, id=id, business=isletme)

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
    try:
        from appointments.tasks import add_appointment_to_calendar_task
        add_appointment_to_calendar_task.delay(randevu.id)
    except Exception as ex:
        print(f"HATA: Takvim senkronize görevi tetiklenemedi: {ex}")

    musteri_adi = f"{randevu.customer.first_name} {randevu.customer.last_name}"
    tarih = randevu.date_time.strftime("%d.%m.%Y %H:%M")
    mesaj = f"Sayın {musteri_adi},\n\n{tarih} tarihli randevunuz {randevu.business.name} tarafından ONAYLANMIŞTIR. Bizi tercih ettiğiniz için teşekkürler."
    html_mesaj = render_to_string('appointments/randevu_onay_email.html', {'randevu': randevu})

    bildirim_gonder(randevu.customer, mesaj, html_mesaj)

    messages.success(request, '✅ Randevu onaylandı, müşteriye e-posta gönderildi ve Google Takviminize senkronize ediliyor!')

    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


# ==========================================
# İŞLETME SAHİBİ RANDEVUYU İPTAL EDİYOR
# ==========================================
@login_required(login_url="/hesap/giris/")
def randevu_iptal(request, id):
    isletme = get_aktif_isletme(request)
    randevu = get_object_or_404(Appointment, id=id, business=isletme)

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
    html_mesaj = render_to_string('appointments/randevu_iptal_email.html', {'randevu': randevu})

    bildirim_gonder(randevu.customer, mesaj, html_mesaj)

    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


@login_required(login_url='/hesap/giris/')
def isletme_randevular(request):
    isletme = get_aktif_isletme(request)
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
        return render(request, 'appointments/islem_tamam.html', {'randevu': randevu})

    if randevu.status == 'completed':
        messages.error(request, "Tamamlanmış bir randevuyu iptal edemezsiniz.")
        return render(request, 'appointments/islem_tamam.html', {'randevu': randevu})

    now = timezone.now()
    kalan_sure = randevu.date_time - now

    # ==========================================
    # 🔥 ZEKİ İPTAL KURALI (BYPASS SİSTEMİ) 🔥
    # ==========================================
    # Eğer patron zorla tarih/uzman değiştirdiyse MÜŞTERİNİN SINIRSIZ HAKKI VARDIR!
    if randevu.is_business_modified:
        iptal_edilebilir_mi = True
    else:
        # Aksi takdirde standart 24 saat kuralı geçerlidir (86400 saniye)
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

            # Celery: Asenkron İptal Bildirimlerini Gönder
            customer_name = f"{randevu.customer.first_name} {randevu.customer.last_name}"
            business_owner_email = randevu.business.owner.email
            appointment_time = randevu.date_time.strftime("%d.%m.%Y %H:%M")
            
            # 1. Müşteriye Bildirim
            iade_ek = " Ücret iadeniz yapılmıştır." if randevu.is_paid else ""
            musteri_mesaj = f"Sayın {customer_name}, {randevu.business.name} randevunuz isteğiniz üzerine iptal edilmiştir.{iade_ek}"
            bildirim_gonder(randevu.customer, musteri_mesaj)
            
            # 2. İşletme Sahibine Bildirim
            if business_owner_email:
                patron_mesaj = f"Randevu İptali! {customer_name}, {appointment_time} tarihli randevusunu kendi isteğiyle iptal etti."
                try:
                    from appointments.tasks import send_email_task
                    send_email_task.delay(
                        subject=f"🚨 Randevu İptali: {customer_name}",
                        message=patron_mesaj,
                        recipient_list=[business_owner_email],
                        from_email=settings.DEFAULT_FROM_EMAIL
                    )
                except Exception as ex:
                    print(f"HATA: Patron iptal maili kuyruğa atılamadı: {ex}")

            return render(request, 'businesses/islem_tamam.html', {'randevu': randevu, 'is_cancel': True})
        else:
            messages.error(request, "Kurallarımız gereği randevunuza 24 saatten az kala iptal işlemi ve ücret iadesi yapılamaz.")

    return render(request, 'appointments/musteri_iptal_onay.html', {
        'randevu': randevu,
        'iptal_edilebilir_mi': iptal_edilebilir_mi,
        'kalan_saat': int(kalan_sure.total_seconds() / 3600) if kalan_sure.total_seconds() > 0 else 0
    })

from django.views.decorators.cache import never_cache

@never_cache
def degerlendirme_yap(request, token):
    randevu = get_object_or_404(Appointment, review_token=token)

    if randevu.is_reviewed:
        return render(request, 'appointments/islem_tamam.html', {'randevu': randevu})

    if request.method == 'POST':
        puan_quality = request.POST.get('rating_quality')
        puan_hospitality = request.POST.get('rating_hospitality')
        puan_cleanliness = request.POST.get('rating_cleanliness')
        puan_value = request.POST.get('rating_value')
        yorum = request.POST.get('comment')

        if puan_quality and puan_hospitality and puan_cleanliness and puan_value:
            rq = int(puan_quality)
            rh = int(puan_hospitality)
            rc = int(puan_cleanliness)
            rv = int(puan_value)
            
            # Ortalama puanı yuvarlayarak tam sayı yap (1-5 arası olmalı)
            overall_rating = int(round((rq + rh + rc + rv) / 4.0))
            if overall_rating < 1: overall_rating = 1
            if overall_rating > 5: overall_rating = 5

            Review.objects.create(
                business=randevu.business,
                appointment=randevu,
                rating=overall_rating,
                rating_quality=rq,
                rating_hospitality=rh,
                rating_cleanliness=rc,
                rating_value=rv,
                comment=yorum
            )
            randevu.is_reviewed = True
            randevu.save()

            messages.success(request, 'Değerlendirmeniz için teşekkür ederiz!')
            return redirect('isletme_detay', slug=randevu.business.slug)
        else:
            # Fallback (Eski şablon veya eksik puanlama olması durumuna karşı)
            puan = request.POST.get('rating')
            if puan:
                p_val = int(puan)
                Review.objects.create(
                    business=randevu.business,
                    appointment=randevu,
                    rating=p_val,
                    rating_quality=p_val,
                    rating_hospitality=p_val,
                    rating_cleanliness=p_val,
                    rating_value=p_val,
                    comment=yorum
                )
                randevu.is_reviewed = True
                randevu.save()

                messages.success(request, 'Değerlendirmeniz için teşekkür ederiz!')
                return redirect('isletme_detay', slug=randevu.business.slug)

    return render(request, 'appointments/degerlendirme_yap.html', {'randevu': randevu})

def get_available_times(request, slug):
    isletme = get_object_or_404(Business, slug=slug)

    date_str = request.GET.get('date')
    service_id = request.GET.get('service_id')
    staff_id = request.GET.get('staff_id')

    if not date_str or not service_id:
        return JsonResponse({'error': 'Eksik parametre'}, status=400)

    try:
        secilen_tarih = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Geçersiz tarih'}, status=400)

    js_gun_kodu = str(secilen_tarih.isoweekday() % 7)

    if isletme.closed_days and js_gun_kodu in isletme.closed_days.split(','):
        return JsonResponse({'slots': [], 'error': 'İşletme bu tarihte (izin günü) kapalıdır.'})

    secilen_hizmet = get_object_or_404(Service, id=service_id, business=isletme)

    sure_dk = 60
    if secilen_hizmet.duration:
        if secilen_hizmet.duration_type == "minutes":
            sure_dk = secilen_hizmet.duration
        elif secilen_hizmet.duration_type == "hours":
            sure_dk = secilen_hizmet.duration * 60
        else:
            # Gün, Hafta, Ay gibi uzun süreli hizmetler "süreç" yönetimidir.
            # Randevu sistemini günlerce kilitlememesi için sadece 1 saatlik (60 dk) planlama bloku ayırıyoruz.
            sure_dk = 60

    acilis = isletme.opening_time
    kapanis = isletme.closing_time

    # 🔥 HIZLANDIRMA 1: Sadece ID'leri bir RAM Listesine alıyoruz! (Döngüde DB'ye sormayacak)
    yetkili_personel_id_listesi = list(secilen_hizmet.staffs.filter(is_active=True, is_approved=True).values_list('id', flat=True))
    toplam_yetkili_sayisi = len(yetkili_personel_id_listesi)

    if toplam_yetkili_sayisi == 0:
        toplam_yetkili_sayisi = 1

    # 🔥 HIZLANDIRMA 2: select_related ile randevunun içindeki hizmeti de tek seferde çekiyoruz!
    gunluk_randevular = isletme.appointments.filter(
        date_time__date=secilen_tarih,
        status__in=['pending', 'approved', 'confirmed']
    ).select_related('service', 'staff')

    slots = []
    suanki_zaman = datetime.datetime.combine(secilen_tarih, acilis)
    kapanis_zamani = datetime.datetime.combine(secilen_tarih, kapanis)
    now = timezone.now()

    # 🔥 EKSTRA ZEKİ KONTROL: Eğer hizmet süresi dükkanın günlük toplam çalışma süresinden fazlaysa (Örn: 27 Saat),
    # Slotları bulurken süreyi 15 dakikaya sabitleyelim ki sistem kilitlenmesin ve patron randevuyu açabilsin.
    isletme_gunluk_sure_dk = (kapanis.hour * 60 + kapanis.minute) - (acilis.hour * 60 + acilis.minute)
    kontrol_suresi = sure_dk if sure_dk <= isletme_gunluk_sure_dk else 15

    while suanki_zaman + timedelta(minutes=kontrol_suresi) <= kapanis_zamani:
        slot_baslangic = suanki_zaman
        slot_bitis = suanki_zaman + timedelta(minutes=kontrol_suresi)

        is_available = True

        aware_slot_baslangic = timezone.make_aware(slot_baslangic) if timezone.is_naive(slot_baslangic) else slot_baslangic
        if aware_slot_baslangic < now:
            is_available = False

        if is_available:
            if staff_id:
                for r in gunluk_randevular:
                    if str(r.staff_id) == str(staff_id):
                        r_sure_dk = 60
                        if r.service and r.service.duration:
                            if r.service.duration_type == "minutes":
                                r_sure_dk = r.service.duration
                            elif r.service.duration_type == "hours":
                                r_sure_dk = r.service.duration * 60
                            
                            if r_sure_dk > isletme_gunluk_sure_dk:
                                r_sure_dk = 60
                                
                        r_baslangic = timezone.localtime(r.date_time).replace(tzinfo=None)
                        r_bitis = r_baslangic + timedelta(minutes=r_sure_dk)

                        if slot_baslangic < r_bitis and slot_bitis > r_baslangic:
                            is_available = False
                            break
            else:
                mesgul_personel_sayisi = 0
                for r in gunluk_randevular:
                    r_sure = 60
                    if r.service and r.service.duration:
                        if r.service.duration_type == "minutes":
                            r_sure = r.service.duration
                        elif r.service.duration_type == "hours":
                            r_sure = r.service.duration * 60
                        
                        if r_sure > isletme_gunluk_sure_dk:
                            r_sure = 60
                    
                    r_baslangic = timezone.localtime(r.date_time).replace(tzinfo=None)
                    r_bitis = r_baslangic + timedelta(minutes=r_sure)

                    if slot_baslangic < r_bitis and slot_bitis > r_baslangic:
                        if r.staff_id:
                            # 🔥 HIZLANDIRMA 3: DB'ye sormak yerine RAM'deki listede var mı diye bakıyoruz! (ŞİMŞEK HIZI)
                            if r.staff_id in yetkili_personel_id_listesi:
                                mesgul_personel_sayisi += 1
                        else:
                            mesgul_personel_sayisi = toplam_yetkili_sayisi
                            break

                if mesgul_personel_sayisi >= toplam_yetkili_sayisi:
                    is_available = False

        slots.append({
            'time': slot_baslangic.strftime('%H:%M'),
            'available': is_available
        })

        suanki_zaman += timedelta(minutes=15)

    return JsonResponse({'slots': slots})

# ==========================================
# 🔥 GOOGLE CALENDAR OAUTH2
# ==========================================
from django.conf import settings as app_settings
if app_settings.DEBUG:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

@login_required(login_url="/hesap/giris/")
def google_takvim_bagla(request):
    isletme = get_aktif_isletme(request)

    if not isletme.is_premium:
        messages.error(request, "Bu özellik sadece Premium işletmelere özeldir.")
        return redirect('isletme_ayarlar')

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "project_id": "kobirandevu",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uris": [request.build_absolute_uri(reverse('google_takvim_callback'))]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=request.build_absolute_uri('/randevu-yonetimi/google/callback/')
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    request.session['google_oauth_state'] = state
    request.session['google_code_verifier'] = getattr(flow, 'code_verifier', None)

    return redirect(authorization_url)

@login_required(login_url="/hesap/giris/")
def google_takvim_callback(request):
    state = request.session.get('google_oauth_state')
    code_verifier = request.session.get('google_code_verifier')

    isletme = get_aktif_isletme(request)
    if not isletme.is_premium:
        messages.error(request, "Bu özellik sadece Premium işletmelere özeldir.")
        return redirect('isletme_ayarlar')

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "project_id": "kobirandevu",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uris": [request.build_absolute_uri(reverse('google_takvim_callback'))]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
        redirect_uri=request.build_absolute_uri('/randevu-yonetimi/google/callback/')
    )

    if code_verifier:
        flow.code_verifier = code_verifier

    authorization_response = request.build_absolute_uri()

    try:
        flow.fetch_token(authorization_response=authorization_response)
    except Exception as e:
        print(f"Token Hatası DETAYI: {e}")
        messages.error(request, "Google onayı sırasında bir güvenlik hatası oluştu. Lütfen tekrar deneyin.")
        return redirect('isletme_ayarlar')

    credentials = flow.credentials

    isletme.google_access_token = credentials.token
    if credentials.refresh_token:
        isletme.google_refresh_token = credentials.refresh_token
    isletme.google_token_expiry = credentials.expiry
    isletme.save()

    if 'google_oauth_state' in request.session:
        del request.session['google_oauth_state']
    if 'google_code_verifier' in request.session:
        del request.session['google_code_verifier']

    messages.success(request, "🎉 Muazzam! Google Takviminiz başarıyla sisteme entegre edildi.")
    return redirect('isletme_ayarlar')


@login_required(login_url="/hesap/giris/")
def google_takvim_kopar(request):
    isletme = get_aktif_isletme(request)

    # Veritabanındaki Google anahtarlarını sıfırlıyoruz
    isletme.google_access_token = None
    isletme.google_refresh_token = None
    isletme.google_token_expiry = None
    isletme.save()

    messages.success(request, "Google Takvim bağlantısı başarıyla kaldırıldı.")
    return redirect('isletme_ayarlar')


# ==========================================
# 🔥 YENİ: TÜM PERSONELLERİ ÇEKEN API (Aktarma Modalı İçin)
# ==========================================
def api_service_staffs(request, slug, service_id):
    isletme = get_object_or_404(Business, slug=slug)

    # Patron zorda kalmış olabilir, dükkandaki TÜM aktif personelleri kurtarıcı olarak listeliyoruz.
    personeller = isletme.staff_members.filter(is_active=True, is_approved=True)

    data = [{"id": p.id, "name": p.name, "title": p.title or "Uzman"} for p in personeller]
    return JsonResponse({"staffs": data})


# ==========================================
# 🔥 YENİ: SADECE PERSONEL AKTARMA MOTORU (KRALIN ZEKASI)
# ==========================================
@login_required(login_url="/hesap/giris/")
def randevu_aktar(request):
    if request.method == "POST":
        isletme = get_aktif_isletme(request)
        if not isletme:
            return redirect("kayit")

        randevu_id = request.POST.get("randevu_id")
        new_staff_id = request.POST.get("new_staff_id")
        new_date = request.POST.get("new_date")
        new_time = request.POST.get("new_time")

        randevu = get_object_or_404(Appointment, id=randevu_id, business=isletme)
        eski_personel_adi = randevu.staff.name if randevu.staff else "Fark Etmez"
        eski_zaman = randevu.date_time.strftime("%d.%m.%Y - %H:%M")

        if not new_date or not new_time:
            messages.error(request, "Lütfen yeni tarih ve saati seçtiğinizden emin olun.")
            return redirect("isletme_randevular")

        try:
            zaman_metni = f"{new_date} {new_time.strip()}"
            import datetime
            yeni_zaman_ham = datetime.datetime.strptime(zaman_metni, "%Y-%m-%d %H:%M")
            from django.utils import timezone
            yeni_zaman = timezone.make_aware(yeni_zaman_ham) if timezone.is_naive(yeni_zaman_ham) else yeni_zaman_ham
        except Exception as e:
            messages.error(request, "Tarih işlenirken bir sorun oluştu.")
            return redirect("isletme_randevular")

        # Yeni Personeli Ata
        if new_staff_id and new_staff_id != "0":
            yeni_personel = get_object_or_404(Staff, id=new_staff_id, business=isletme)
            randevu.staff = yeni_personel
            yeni_personel_adi = yeni_personel.name
        else:
            randevu.staff = None
            yeni_personel_adi = "Herhangi Bir Uzman"

        randevu.date_time = yeni_zaman
        randevu.is_business_modified = True
        randevu.save()

        # ==========================================
        # 🔥 MÜŞTERİYE HTML BİLDİRİM (ŞABLONDAN) 🔥
        # ==========================================
        from django.template.loader import render_to_string

        yeni_tarih_str = randevu.date_time.strftime("%d.%m.%Y")
        yeni_saat_str = randevu.date_time.strftime("%H:%M")

        # 🔥 KRİTİK ÇÖZÜM: musteri_adi değişkeni eklendi! 🔥
        musteri_adi = f"{randevu.customer.first_name} {randevu.customer.last_name}"
        iptal_linki = request.build_absolute_uri(reverse('musteri_iptal_linki', args=[randevu.cancel_token]))

        context = {
            'randevu': randevu,
            'eski_zaman': eski_zaman,
            'eski_personel_adi': eski_personel_adi,
            'yeni_tarih_str': yeni_tarih_str,
            'yeni_saat_str': yeni_saat_str,
            'yeni_personel_adi': yeni_personel_adi,
            'iptal_linki':iptal_linki,
        }

        # HTML render etme kodları
        html_icerik = render_to_string('appointments/randevu_aktar_email.html', context)

        # Sadece düz metin yollayacağımız değişken (SMS için falan da kullanılır)
        duz_metin = f"Sayın {musteri_adi}, randevunuz {yeni_tarih_str} ({yeni_personel_adi}) olarak güncellenmiştir."

        try:
            bildirim_gonder(randevu.customer, mesaj=duz_metin, html_mesaj=html_icerik)
        except Exception as e:
            print(f"BİLDİRİM HATASI: {e}")

        messages.success(request, f"🔄 Randevu aktarıldı! Müşteriye bilgilendirme e-postası gönderildi.")
        return redirect("isletme_randevular")

    return redirect("isletme_randevular")


from django.utils.dateparse import parse_datetime

@login_required(login_url='/hesap/giris/')
def api_calendar_events(request):
    """ Takvime sadece o an ekranda görünen tarih aralığındaki randevuları gönderir """
    isletme = get_aktif_isletme(request)
    if not isletme:
        return JsonResponse([], safe=False)

    start_str = request.GET.get('start')
    end_str = request.GET.get('end')

    # YENİ: select_related ile 3 kat daha hızlı sorgu
    randevular = isletme.appointments.filter(
        status__in=['pending', 'confirmed']
    ).select_related('customer', 'service', 'staff')

    # YENİ: Sadece o haftayı/ayı filtrele
    if start_str and end_str:
        try:
            start_date = parse_datetime(start_str)
            end_date = parse_datetime(end_str)
            if start_date and end_date:
                randevular = randevular.filter(date_time__gte=start_date, date_time__lte=end_date)
        except Exception:
            pass

    events = []
    for r in randevular:
        sure_dk = 60
        if r.service and r.service.duration:
            if r.service.duration_type == 'minutes':
                sure_dk = r.service.duration
            elif r.service.duration_type == 'hours':
                sure_dk = r.service.duration * 60

        bitis = r.date_time + timedelta(minutes=sure_dk)

        if r.status == "pending":
            color = "#f59e0b" if isletme.is_premium else "#6366f1"
        else:
            color = "#10b981"

        events.append({
            "id": r.id,
            "title": f"{r.customer.first_name} ({r.service.name})",
            "start": r.date_time.isoformat(),
            "end": bitis.isoformat(),
            "resourceId": str(r.staff.id) if r.staff else "farketmez",
            "color": color,
            "extendedProps": {
                "status": r.status,
                "customer_name": f"{r.customer.first_name} {r.customer.last_name}",
                "phone": r.customer.phone,
                "staff_name": r.staff.name if r.staff else "Fark Etmez"
            }
        })

    return JsonResponse(events, safe=False)


@login_required(login_url='/hesap/giris/')
def api_calendar_resources(request):
    """ Takvimin üstündeki Personel Sütunlarını (Resource) gönderir (SADECE PREMİUM) """
    isletme = get_aktif_isletme(request)
    if not isletme or not isletme.is_premium:
        return JsonResponse([], safe=False)

    resources = []
    # Dükkandaki personelleri sütun olarak ekle
    for staff in isletme.staff_members.filter(is_active=True):
        resources.append({
            "id": str(staff.id),
            "title": staff.name
        })

    # Bir de 'Fark Etmez' (Personelsiz) randevular için sütun ekleyelim
    resources.append({
        "id": "farketmez",
        "title": "Atanmamış / Boşta"
    })

    return JsonResponse(resources, safe=False)


@login_required(login_url='/hesap/giris/')
def takvim_gorunumu(request):
    isletme = get_aktif_isletme(request)
    if not isletme:
        return redirect('kayit')

    return render(request, 'appointments/takvim.html', {'isletme': isletme})

import threading  # 🔥 EKLENDİ: Sayfanın üst kısmına, diğer importların yanına koyun

# ==========================================
# 🔥 YENİ: TAKVİMDEN HIZLI (MANUEL) RANDEVU OLUŞTURMA 🔥
# ==========================================
@login_required(login_url="/hesap/giris/")
def manuel_randevu_olustur(request):
    if request.method == 'POST':
        isletme = get_aktif_isletme(request)
        if not isletme:
            return redirect('kayit')

        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name', '')
        phone = request.POST.get('phone')
        email = request.POST.get('email', '') # 🔥 YENİ: E-posta eklendi
        service_id = request.POST.get('service_id')
        staff_id = request.POST.get('staff_id')
        date_str = request.POST.get('date')
        time_str = request.POST.get('time')
        payment_type = request.POST.get('payment_type')

        try:
            zaman_metni = f"{date_str} {time_str.strip()}"
            yeni_zaman_ham = datetime.datetime.strptime(zaman_metni, "%Y-%m-%d %H:%M")
            yeni_zaman = timezone.make_aware(yeni_zaman_ham) if timezone.is_naive(yeni_zaman_ham) else yeni_zaman_ham
        except Exception:
            messages.error(request, "Geçersiz tarih veya saat formatı.")
            return redirect('takvim_gorunumu')

        service = get_object_or_404(Service, id=service_id, business=isletme)
        staff = get_object_or_404(Staff, id=staff_id, business=isletme) if staff_id else None

        # Müşteriyi bul veya yarat (E-posta güncellenir)
        customer = Customer.objects.filter(phone=phone, business=isletme).first()
        if not customer:
            customer = Customer.objects.create(
                business=isletme,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email  # Yeni müşteri ise e-postasını kaydet
            )
        elif email and not customer.email:
            # Eski müşteri ama e-postası yoksa, şimdi girilmişse güncelle
            customer.email = email
            customer.save()

        # Randevu statüsünü ödeme tipine göre belirle
        if payment_type == 'cash':
            randevu_status = 'confirmed'
            is_paid_status = True
        else:
            # 🔥 PAZARYERİ GÜVENLİK KONTROLÜ 🔥
            # IBAN (subMerchantKey) olmayan işletmeler link gönderemez, böylece sistemin ana havuzu suistimal edilemez.
            if not isletme.iyzico_sub_merchant_key:
                messages.error(request, "Online ödeme linki gönderebilmek için Ayarlar bölümünden IBAN ve Vergi bilgilerinizi eksiksiz doldurup Iyzico kaydınızı tamamlamanız gerekmektedir. Güvenlik sebebiyle şu an sadece nakit veya elden ödeme alabilirsiniz.")
                return redirect('takvim_gorunumu')
                
            # Link gönderiliyorsa 'pending' başlasın
            randevu_status = 'pending'
            is_paid_status = False

        # Randevuyu sisteme kaydet
        try:
            from django.db import IntegrityError
            randevu = Appointment.objects.create(
                business=isletme,
                customer=customer,
                service=service,
                staff=staff,
                date_time=yeni_zaman,
                status=randevu_status,
                chosen_location='in_store',
                final_service_price=service.discounted_price if service.has_campaign else service.price,
                total_online_charged=(service.discounted_price if service.has_campaign else service.price) + Decimal('5.00'),
                is_paid=is_paid_status
            )
        except IntegrityError:
            messages.error(request, "🚨 Çakışma Hatası: Seçtiğiniz personel için bu tarih ve saatte zaten aktif bir randevu mevcut. Lütfen başka bir saat seçin.")
            return redirect('takvim_gorunumu')

        # ==========================================
        # 🔥 GOOGLE TAKVİM KAYDINI CELERY'E ATTIK 🔥
        # ==========================================
        try:
            from appointments.tasks import add_appointment_to_calendar_task
            add_appointment_to_calendar_task.delay(randevu.id)
        except Exception as e:
            print(f"Google Takvim asenkron işlemi başlatılamadı: {e}")

        if payment_type == 'link':
            # 🔥 YENİ: DJANGO'NUN GERÇEK ÖDEME LİNKİNİ OLUŞTURUYORUZ 🔥
            odeme_linki = request.build_absolute_uri(reverse('randevu_odeme_ozeti', kwargs={'token': randevu.cancel_token}))

            mesaj = f"Sayın {first_name}, {isletme.name} randevunuz oluşturuldu. Kesinleştirmek için ödemenizi şu linkten yapabilirsiniz: {odeme_linki}"
            
            # HTML Mail Şablonunu Hazırla
            html_mesaj = render_to_string('appointments/payment_link_email.html', {
                'randevu': randevu,
                'payment_url': odeme_linki,
            })

            bildirim_gonder(customer, mesaj, html_mesaj=html_mesaj)
            messages.success(request, "Randevu oluşturuldu ve müşteriye Premium Ödeme Maili gönderildi!")
        else:
            mesaj = f"Sayın {first_name}, {yeni_zaman.strftime('%d.%m.%Y %H:%M')} tarihli randevunuz {isletme.name} tarafından başarıyla oluşturulmuştur."
            bildirim_gonder(customer, mesaj)
            messages.success(request, "Randevu takvime başarıyla eklendi ve müşteriye bilgilendirme gönderildi.")

        return redirect('takvim_gorunumu')

    return redirect('takvim_gorunumu')