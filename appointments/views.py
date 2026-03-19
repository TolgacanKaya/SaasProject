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

from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string


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

    musteri_adi = f"{randevu.customer.first_name} {randevu.customer.last_name}"
    tarih = randevu.date_time.strftime("%d.%m.%Y %H:%M")
    mesaj = f"Sayın {musteri_adi},\n\n{tarih} tarihli randevunuz {randevu.business.name} tarafından ONAYLANMIŞTIR. Bizi tercih ettiğiniz için teşekkürler."
    html_mesaj = render_to_string('businesses/randevu_onay_email.html', {'randevu': randevu})

    bildirim_gonder(randevu.customer, mesaj, html_mesaj)
    messages.success(request, '✅ Randevu onaylandı ve müşteriye bildirim gönderildi.')

    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


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

    randevu.status = 'cancelled'
    randevu.save()

    musteri_adi = f"{randevu.customer.first_name} {randevu.customer.last_name}"
    # İYİLEŞTİRME: İşletme telefonu eklendi
    mesaj = f"Sayın {musteri_adi},\n\n{randevu.business.name} işletmesindeki randevunuz maalesef İPTAL edilmiştir. Detaylı bilgi veya yeni randevu için işletme ile ({randevu.business.phone}) iletişime geçebilirsiniz."
    html_mesaj = render_to_string('businesses/randevu_iptal_email.html', {'randevu': randevu})

    bildirim_gonder(randevu.customer, mesaj, html_mesaj)
    messages.error(request, '❌ Randevu iptal edildi ve müşteriye bildirim gönderildi.')

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
# MÜŞTERİ KENDİ RANDEVUSUNU İPTAL EDİYOR
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

    iptal_edilebilir_mi = kalan_sure.total_seconds() > 86400

    if request.method == 'POST':
        if iptal_edilebilir_mi:
            randevu.status = 'customer_cancelled'
            randevu.save()
            messages.success(request,
                             "Randevunuz başarıyla iptal edildi. Ödemeniz 1-3 iş günü içerisinde kartınıza iade edilecektir.")
            return render(request, 'businesses/islem_tamam.html', {'randevu': randevu, 'is_cancel': True})
        else:
            messages.error(request, "Kurallarımız gereği randevunuza 24 saatten az kala iptal işlemi yapılamaz.")

    return render(request, 'appointments/musteri_iptal_onay.html', {
        'randevu': randevu,
        'iptal_edilebilir_mi': iptal_edilebilir_mi,
        'kalan_saat': int(kalan_sure.total_seconds() / 3600) if kalan_sure.total_seconds() > 0 else 0
    })