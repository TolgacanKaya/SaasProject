from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Appointment
from django.core.paginator import Paginator
from businesses.models import Business
from django.db.models import Case, When, Value, IntegerField  # YENİ: Akıllı sıralama için eklendi


# --- YARDIMCI FONKSİYON: SMS GÖNDERİMİ ---
def sms_gonder(telefon, mesaj):
    """
    Bu fonksiyon gerçek hayatta bir SMS API'sine (Örn: Netgsm, Twilio) istek atar.
    Şu an demo amaçlı konsola çıktı veriyoruz.
    """
    if not telefon:
        return False

    # Telefon numarasındaki boşlukları temizleyelim
    temiz_telefon = telefon.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    # Konsola Log Düşelim (Öğretmenine burayı gösterebilirsin)
    print(f"📨 [SMS SİMÜLASYONU] Kime: {temiz_telefon} | Mesaj: {mesaj}")

    return True


@login_required(login_url="/hesap/giris/")
def randevu_onayla(request, id):
    randevu = get_object_or_404(Appointment, id=id, business__owner=request.user)

    randevu.status = 'approved'
    randevu.save()

    # SMS GÖNDER
    musteri_adi = f"{randevu.customer.first_name} {randevu.customer.last_name}"
    tarih = randevu.date_time.strftime("%d.%m.%Y %H:%M")
    mesaj = f"Sayin {musteri_adi}, {tarih} tarihli randevunuz {randevu.business.name} tarafindan ONAYLANMISTIR. Bizi tercih ettiginiz icin tesekkurler."

    sms_gonder(randevu.customer.phone, mesaj)

    messages.success(request, '✅ Randevu onaylandı ve müşteriye SMS gönderildi.')

    # GELDİĞİ SAYFAYA GERİ DÖN:
    onceki_sayfa = request.META.get('HTTP_REFERER')
    if not onceki_sayfa:
        return redirect('dashboard')
    return redirect(onceki_sayfa)


@login_required(login_url="/hesap/giris/")
def randevu_iptal(request, id):
    randevu = get_object_or_404(Appointment, id=id, business__owner=request.user)

    randevu.status = 'cancelled'
    randevu.save()

    # SMS GÖNDER
    musteri_adi = f"{randevu.customer.first_name} {randevu.customer.last_name}"
    mesaj = f"Sayin {musteri_adi}, randevunuz maalesef IPTAL edilmistir. Detayli bilgi icin isletme ile iletisime gecebilirsiniz."

    sms_gonder(randevu.customer.phone, mesaj)

    messages.error(request, '❌ Randevu iptal edildi ve müşteriye SMS gönderildi.')

    # GELDİĞİ SAYFAYA GERİ DÖN:
    onceki_sayfa = request.META.get('HTTP_REFERER')
    if not onceki_sayfa:
        return redirect('dashboard')
    return redirect(onceki_sayfa)


@login_required(login_url='/hesap/giris/')
def isletme_randevular(request):
    isletme = Business.objects.filter(owner=request.user).first()
    if not isletme:
        return redirect('kayit')

    # ==========================================
    # AKILLI SIRALAMA ALGORİTMASI (UX ODAKLI)
    # ==========================================
    # 1. Bekleyen (pending) randevular her zaman EN ÜSTTE olacak.
    # 2. Sonra Onaylanmış ve İptal edilmiş olanlar gelecek.
    # 3. Kendi içlerinde ise tarihe göre (en yakın tarihten uzağa) sıralanacak.

    tum_randevular_list = isletme.appointments.all().annotate(
        oncelik_sirasi=Case(
            When(status='pending', then=Value(1)),  # Bekleyenlere VIP bilet (1)
            default=Value(2),  # Geri kalanlara normal bilet (2)
            output_field=IntegerField(),
        )
    ).order_by('oncelik_sirasi', 'date_time')

    # SAYFALANDIRMA: Sayfa başına 10 randevu göster
    paginator = Paginator(tum_randevular_list, 10)
    page = request.GET.get('page')
    randevular = paginator.get_page(page)

    return render(request, 'appointments/isletme_randevular.html', {'isletme': isletme, 'randevular': randevular})